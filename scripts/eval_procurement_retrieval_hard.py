from __future__ import annotations

import json
import os
import time
from pathlib import Path

from eval_procurement_ablation import (
    DEFAULT_PIPELINES,
    HARD_PRIMARY_TITLES,
    PROCUREMENT_USER,
    _average,
    _doc_rank_metrics,
    _embedding_backend,
    _retrieve_for_strategy,
    _warm_up_embedding_if_needed,
    ingest_procurement_only,
)
from app.services.evaluation.procurement_review_cases import PROCUREMENT_REVIEW_EVAL_CASES


def _hard_query_for_case(case) -> str:
    data_signals: list[str] = []
    if case.vendor.handles_company_data:
        data_signals.append("会接触客户资料、业务记录或员工信息")
    if case.vendor.requires_system_integration:
        data_signals.append("需要打通内部账号、接口或业务系统")
    if case.vendor.quoted_amount > case.project.budget_amount:
        data_signals.append("费用超过原预算，需要确认审批层级")
    if "source" in case.scenario_type:
        data_signals.append("来源链路不清，需要核验真实公司主体")
    if "capability" in case.scenario_type:
        data_signals.append("产品介绍偏通用，需要确认是否覆盖专业业务场景")

    return "\n".join(
        [
            f"采购需求：{case.project.department}引入{case.project.title}，{case.project.summary}",
            f"供应商描述：{case.vendor.profile_summary}",
            f"采购备注：{case.vendor.procurement_notes}",
            "风险线索：" + "；".join(data_signals or ["常规供应商准入核验"]),
            f"关注点：{case.vendor.focus_points or '根据企业采购制度查找主依据'}",
        ]
    )


def run_hard_retrieval_eval() -> dict[str, object]:
    started = time.perf_counter()
    case_limit_raw = (os.getenv("PROC_RETRIEVAL_HARD_CASE_LIMIT") or "").strip()
    case_limit = int(case_limit_raw) if case_limit_raw.isdigit() and int(case_limit_raw) > 0 else 0
    cases = PROCUREMENT_REVIEW_EVAL_CASES[:case_limit] if case_limit else PROCUREMENT_REVIEW_EVAL_CASES
    print("[retrieval-hard] preparing temporary procurement index", flush=True)
    container, db, ingested_docs = ingest_procurement_only(
        skip_index_embeddings=True,
        tmp_dir_name=f"tmp_eval_procurement_retrieval_hard_work_{os.getpid()}",
    )
    print(f"[retrieval-hard] indexed docs={len(ingested_docs)} cases={len(cases)}", flush=True)
    _warm_up_embedding_if_needed(container, "semantic_only")
    summary: dict[str, object] = {
        "benchmark_version": "procurement_retrieval_hard_v1",
        "case_count": len(cases),
        "docs": list(ingested_docs),
        "doc_count": len(ingested_docs),
        "embedding_backend": _embedding_backend(container),
        "embedding_dimension": container.embedding_service.dimensions,
        "pipelines": {},
    }

    try:
        for pipeline in DEFAULT_PIPELINES:
            if pipeline != "bm25_only":
                _warm_up_embedding_if_needed(container, pipeline)
            pipeline_started = time.perf_counter()
            hit1_scores: list[float] = []
            hit5_scores: list[float] = []
            mrr_scores: list[float] = []
            failures: list[dict[str, object]] = []
            for index, case in enumerate(cases, start=1):
                if index == 1 or index == len(cases) or index % 10 == 0:
                    print(f"[retrieval-hard] pipeline={pipeline} progress={index}/{len(cases)}", flush=True)
                acceptable = HARD_PRIMARY_TITLES.get(case.scenario_type, case.expected.acceptable_titles)
                query = _hard_query_for_case(case)
                retrieved, _debug = _retrieve_for_strategy(
                    container.retrieval_service,
                    strategy=pipeline,
                    db=db,
                    query=query,
                    user_role=PROCUREMENT_USER.role,
                    top_k=5,
                    plan=container.agent_service.llm_client.build_retrieval_plan(query, "procurement_fit_review", 5),
                )
                returned_titles = [item.document_title for item in retrieved]
                hit1, hit5, mrr = _doc_rank_metrics(returned_titles, acceptable)
                hit1_scores.append(hit1)
                hit5_scores.append(hit5)
                mrr_scores.append(mrr)
                if hit5 == 0.0:
                    failures.append(
                        {
                            "case_id": case.case_id,
                            "scenario_type": case.scenario_type,
                            "acceptable_titles": list(acceptable),
                            "returned_titles": returned_titles,
                            "query": query,
                        }
                    )

            summary["pipelines"][pipeline] = {
                "hit@1": _average(hit1_scores),
                "hit@5": _average(hit5_scores),
                "mrr": _average(mrr_scores),
                "embedding_backend": _embedding_backend(container),
                "embedding_dimension": container.embedding_service.dimensions,
                "failures": failures[:12],
                "elapsed_seconds": round(time.perf_counter() - pipeline_started, 2),
            }
    finally:
        db.close()

    summary["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    return summary


if __name__ == "__main__":
    result = run_hard_retrieval_eval()
    out_dir = Path.cwd() / "tmp_eval_procurement_retrieval_hard"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "retrieval_hard_result.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[retrieval-hard] compact summary")
    print(f"  result_file: {out_path}")
    print(
        f"  cases={result['case_count']} docs={result.get('doc_count')} "
        f"embedding={result.get('embedding_backend')}({result.get('embedding_dimension')}) "
        f"elapsed={result['elapsed_seconds']}s"
    )
    for name, metrics in result["pipelines"].items():
        print(
            f"  {name}: hit@1={metrics['hit@1']} hit@5={metrics['hit@5']} "
            f"mrr={metrics['mrr']} embedding={metrics['embedding_backend']}({metrics['embedding_dimension']}) "
            f"elapsed={metrics['elapsed_seconds']}s"
        )
