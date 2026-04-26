from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import MethodType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import build_settings
from app.core.container import AppContainer
from app.db.init_db import init_db
from app.db.session import create_session_factory
from app.models.entities import ProcurementStage
from app.repositories.auth_repository import AuthRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.auth import UserProfileRead
from app.schemas.project import (
    ProcurementAgentReviewRequest,
    ProjectCreate,
    ProjectManagerDecisionRequest,
    ProjectSubmitRequest,
)
from app.services.agent.llm import LLMClient
from app.services.agent.service import KnowledgeOpsAgentService
from app.services.auth_service import AuthService
from app.services.evaluation.procurement_review_cases import PROCUREMENT_REVIEW_EVAL_CASES
from app.services.evaluation.service import EvaluationService
from app.services.ingestion.connectors import DocumentParser
from app.services.ingestion.service import IngestionService
from app.services.project_service import ProjectService
from app.services.retrieval.embeddings import EmbeddingService
from app.services.retrieval.rerankers import _select_top_chunks
from app.services.retrieval.service import RetrievalService


PROCUREMENT_DOC_PREFIX = "采购核心-"
EMBEDDING_MODEL_PATH = r"D:\Models\BAAI\bge-base-zh-v1___5"
RERANKER_MODEL_PATH = r"D:\Models\bge-reranker-base"
DEFAULT_PIPELINES = ("bm25_only", "semantic_only", "hybrid_rrf")
PROGRESS_EVERY = 10
DEFAULT_BENCHMARK_MODE = "hard"

HARD_PRIMARY_TITLES = {
    "analysis_clean": ("采购核心-供应商准入办法.md", "采购核心-供应商背景核验清单.md"),
    "analysis_budget_attention": ("采购核心-预算例外处理说明.md", "采购核心-采购审批矩阵.md"),
    "analysis_data_review": ("采购核心-安全评审操作流程.md", "采购核心-系统接入类采购补充要求.md"),
    "analysis_source_identity": ("采购核心-供应商背景核验清单.md", "采购核心-供应商准入办法.md"),
    "analysis_capability_gap": ("采购核心-外包与服务类供应商筛选要点.md", "采购核心-供应商准入办法.md"),
}

HARD_QUERY_REPLACEMENTS = {
    "安全问卷或安全白皮书": "供应商安全能力证明材料",
    "数据处理说明或隐私/DPA材料": "客户资料使用边界和隐私处理材料",
    "数据存储/部署/数据流说明": "资料保存位置和流转路径说明",
    "安全事件通知承诺": "发生安全问题后的通知时限承诺",
    "是否处理公司/客户数据：是": "会接触客户资料或业务记录",
    "是否处理公司/客户数据：否": "不接触客户资料或业务记录",
    "是否需要系统对接：是": "需要打通内部账号或业务系统",
    "是否需要系统对接：否": "不需要打通内部账号或业务系统",
    "涉及数据处理：customer_data": "处理客户相关信息",
    "数据存储地点未说明": "未说明资料保存在哪里",
    "分包情况：mentioned": "可能依赖第三方或外部服务",
    "预算例外": "费用超过原预算时如何处理",
    "采购审批矩阵": "不同金额对应的审批层级",
    "超预算审批": "超出预算后的审批要求",
    "第三方数据处理": "外部服务商接触客户资料",
    "安全评审": "上线前的信息安全核查",
    "数据处理说明": "客户资料使用说明",
    "隐私DPA材料": "隐私和资料处理承诺",
    "系统接入": "内部账号或业务系统打通",
    "接口权限": "账号、接口和访问范围",
    "接入风险": "内部系统连接带来的风险",
    "可追溯公开来源": "能直接核验的正式来源",
    "供应商主体核验": "确认真实公司主体",
    "供应商背景核验": "确认真实公司主体和背景",
}

PROCUREMENT_USER = UserProfileRead(
    id="eval-procurement",
    username="eval-procurement",
    display_name="Eval Procurement",
    role="procurement",
    department="evaluation",
    status="active",
)


def create_eval_container(settings) -> AppContainer:
    session_factory = create_session_factory(settings)
    embedding_service = EmbeddingService(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )
    document_repository = DocumentRepository()
    retrieval_service = RetrievalService(
        document_repository,
        embedding_service,
        reranker_model=settings.reranker_model,
        reranker_device=settings.reranker_device,
        reranker_enabled=settings.reranker_enabled,
    )
    ingestion_service = IngestionService(
        settings=settings,
        repository=document_repository,
        parser=DocumentParser(),
        embedding_service=embedding_service,
        session_factory=session_factory,
    )
    llm_client = LLMClient(
        api_base=settings.openai_api_base,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
    )
    agent_service = KnowledgeOpsAgentService(
        chat_repository=ChatRepository(),
        retrieval_service=retrieval_service,
        llm_client=llm_client,
    )
    auth_service = AuthService(repository=AuthRepository())
    evaluation_service = EvaluationService(
        repository=EvaluationRepository(),
        agent_service=agent_service,
    )
    project_service = ProjectService(
        repository=ProjectRepository(),
        agent_service=agent_service,
        storage_dir=settings.storage_dir,
    )
    return AppContainer(
        settings=settings,
        session_factory=session_factory,
        embedding_service=embedding_service,
        retrieval_service=retrieval_service,
        ingestion_service=ingestion_service,
        agent_service=agent_service,
        auth_service=auth_service,
        evaluation_service=evaluation_service,
        project_service=project_service,
    )


def ingest_procurement_only(
    *,
    skip_index_embeddings: bool = False,
    tmp_dir_name: str = "tmp_eval_procurement_ablation",
) -> tuple[AppContainer, object, tuple[str, ...]]:
    base = Path.cwd()
    tmp_dir = base / tmp_dir_name
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    settings = build_settings(
        database_url=f"sqlite:///{(tmp_dir / 'eval.db').as_posix()}",
        storage_dir=str(tmp_dir / "uploads"),
        embedding_model="" if skip_index_embeddings else EMBEDDING_MODEL_PATH,
        embedding_device=os.getenv("PROC_EVAL_EMBEDDING_DEVICE", "cpu"),
        reranker_model=RERANKER_MODEL_PATH,
        reranker_device=os.getenv("PROC_EVAL_RERANKER_DEVICE", "cpu"),
        reranker_enabled=True,
    )
    container = create_eval_container(settings)
    init_db(container.session_factory)
    db = container.session_factory()
    container.auth_service.seed_demo_users(db)

    ingested_docs: list[str] = []
    data_dir = base / "data"
    for path in sorted(data_dir.iterdir(), key=lambda item: item.name):
        if path.is_dir() or not path.name.startswith(PROCUREMENT_DOC_PREFIX):
            continue
        response = container.ingestion_service.submit_ingestion(
            db,
            name=path.name,
            data=path.read_bytes(),
            allowed_roles=["employee"],
            tags="baseline,procurement",
            source_path=str(path),
        )
        db.commit()
        container.ingestion_service.run_indexing_task(response.task_id)
        ingested_docs.append(path.name)
    if skip_index_embeddings:
        container.embedding_service.model_name = EMBEDDING_MODEL_PATH
        container.embedding_service._model = None
        container.embedding_service._using_sentence_transformer = False
    return container, db, tuple(sorted(ingested_docs))


def _harden_retrieval_query(query: str) -> str:
    hardened = query
    for source, target in HARD_QUERY_REPLACEMENTS.items():
        hardened = hardened.replace(source, target)
    return hardened


def _enable_hard_query_mode(container: AppContainer) -> None:
    project_service = container.project_service
    original_builder = project_service._build_procurement_agent_query

    def _patched_builder(self, *args, **kwargs):
        return _harden_retrieval_query(original_builder(*args, **kwargs))

    project_service._build_procurement_agent_query = MethodType(_patched_builder, project_service)


def _retrieve_for_strategy(
    retrieval_service: RetrievalService,
    *,
    strategy: str,
    db,
    query: str,
    user_role: str,
    top_k: int,
    plan: dict[str, object] | None = None,
):
    variants = retrieval_service.build_query_variants(query, plan)
    source_type_hints = [str(item) for item in (plan or {}).get("source_type_hints", [])]
    document_hints = [str(item) for item in (plan or {}).get("document_hints", [])]
    accessible_chunks = retrieval_service._load_accessible_chunks(db, user_role=user_role)
    candidate_limit = max(top_k * 6, 12)

    bm25_candidates = retrieval_service._bm25_retrieve(
        variants=variants,
        records=accessible_chunks,
        candidate_limit=candidate_limit,
        source_type_hints=source_type_hints,
        document_hints=document_hints,
    )
    semantic_candidates = retrieval_service._semantic_retrieve(
        db,
        variants=variants,
        user_role=user_role,
        candidate_limit=candidate_limit,
        source_type_hints=source_type_hints,
        document_hints=document_hints,
        accessible_chunks=accessible_chunks,
    )

    if strategy == "bm25_only":
        selected = _select_top_chunks(bm25_candidates, top_k=top_k)
        rerank_debug = {"rerank_strategy": "disabled", "cross_encoder_active": False}
    elif strategy == "semantic_only":
        selected = _select_top_chunks(semantic_candidates, top_k=top_k)
        rerank_debug = {"rerank_strategy": "disabled", "cross_encoder_active": False}
    elif strategy == "hybrid_rrf":
        merged = retrieval_service._merge_candidates_rrf(bm25_candidates, semantic_candidates)
        selected = retrieval_service._select_procurement_rrf_chunks(
            merged,
            bm25_candidates=bm25_candidates,
            top_k=top_k,
        )
        rerank_debug = {"rerank_strategy": "bm25_anchor_rrf", "cross_encoder_active": False}
    elif strategy == "hybrid_rrf_rerank":
        return retrieval_service.retrieve(
            db,
            query=query,
            user_role=user_role,
            top_k=top_k,
            plan=plan,
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    merged_count = 0 if strategy in {"bm25_only", "semantic_only"} else len(
        retrieval_service._merge_candidates_rrf(bm25_candidates, semantic_candidates)
    )
    return selected, {
        "original_query": query,
        "rewritten_query": variants[1] if len(variants) > 1 else query,
        "query_variants": variants,
        "document_hints": document_hints,
        "domain_labels": list((plan or {}).get("domain_labels", [])),
        "bm25_candidate_count": len(bm25_candidates),
        "semantic_candidate_count": len(semantic_candidates),
        "rrf_merged_candidate_count": merged_count,
        "keyword_candidate_count": len(bm25_candidates),
        "vector_candidate_count": len(semantic_candidates),
        "merged_candidate_count": merged_count,
        **rerank_debug,
    }


@contextmanager
def _override_retrieve(container: AppContainer, strategy: str):
    if strategy == "hybrid_rrf_rerank":
        yield
        return

    retrieval_service = container.retrieval_service
    original_retrieve = retrieval_service.retrieve

    def _patched(self, db, *, query: str, user_role: str, top_k: int, plan: dict[str, object] | None = None):
        return _retrieve_for_strategy(
            self,
            strategy=strategy,
            db=db,
            query=query,
            user_role=user_role,
            top_k=top_k,
            plan=plan,
        )

    retrieval_service.retrieve = MethodType(_patched, retrieval_service)
    try:
        yield
    finally:
        retrieval_service.retrieve = original_retrieve


def _doc_rank_metrics(returned_titles: list[str], acceptable_titles: tuple[str, ...]) -> tuple[float, float, float]:
    acceptable = set(acceptable_titles)
    hit1 = 1.0 if returned_titles[:1] and returned_titles[0] in acceptable else 0.0
    hit5 = 1.0 if any(title in acceptable for title in returned_titles[:5]) else 0.0
    mrr = 0.0
    for index, title in enumerate(returned_titles, start=1):
        if title in acceptable:
            mrr = 1.0 / index
            break
    return hit1, hit5, mrr


def _expected_for_mode(case, benchmark_mode: str):
    if benchmark_mode != "hard":
        return case.expected
    primary_titles = HARD_PRIMARY_TITLES.get(case.scenario_type)
    if not primary_titles:
        return case.expected
    return replace(case.expected, acceptable_titles=primary_titles)


def _required_recall(predicted: list[str], required: tuple[str, ...]) -> float:
    required_set = set(required)
    if not required_set:
        return 1.0
    return len(set(predicted) & required_set) / len(required_set)


def _forbidden_violation(predicted: list[str], forbidden: tuple[str, ...]) -> float:
    forbidden_set = set(forbidden)
    if not forbidden_set:
        return 0.0
    return 1.0 if set(predicted) & forbidden_set else 0.0


def _case_success(
    *,
    analysis_tags: list[str],
    missing_materials: list[str],
    evidence_titles: list[str],
    expected,
) -> float:
    _doc_hit1, doc_hit5, _doc_mrr = _doc_rank_metrics(evidence_titles, expected.acceptable_titles)
    return 1.0 if (
        _required_recall(analysis_tags, expected.required_analysis_tags) == 1.0
        and _forbidden_violation(analysis_tags, expected.forbidden_analysis_tags) == 0.0
        and _required_recall(missing_materials, expected.required_missing_materials) == 1.0
        and _forbidden_violation(missing_materials, expected.forbidden_missing_materials) == 0.0
        and doc_hit5 == 1.0
    ) else 0.0


def _run_case(container: AppContainer, db, *, case, index: int, pipeline: str):
    project_detail = container.project_service.create_project(
        db,
        ProjectCreate(
            title=f"[{pipeline}] {case.project.title} #{index:03d}",
            requester_name="评测业务",
            department=case.project.department,
            vendor_name="",
            category=case.project.category,
            budget_amount=case.project.budget_amount,
            currency=case.project.currency,
            summary=case.project.summary,
            business_value=case.project.business_value,
            target_go_live_date="2026-12-31",
            data_scope=case.project.data_scope,
        ),
        created_by_user_id="eval-business",
    )
    container.project_service.submit_project(
        db,
        project_detail.id,
        ProjectSubmitRequest(actor_role="business", reason="离线评测提交"),
    )
    project = container.project_service.repository.get_project(db, project_detail.id)
    if project is None:
        raise ValueError("Project not found after submission.")
    for task in container.project_service.repository.list_tasks(db, project.id):
        if task.stage == ProcurementStage.manager_review.value and task.required:
            task.status = "done"
            task.details = "离线评测自动完成上级审批待办。"
    for artifact in container.project_service.repository.list_artifacts(db, project.id):
        if artifact.stage == ProcurementStage.manager_review.value and artifact.required:
            artifact.status = "provided"
            artifact.direction = "internal"
            artifact.version_no = max(int(artifact.version_no or 1), 1)
            artifact.notes = "离线评测自动提供上级审批意见。"
    container.project_service._refresh_active_stage_blocking_reason(db, project)
    db.commit()
    container.project_service.manager_decision(
        db,
        project_detail.id,
        ProjectManagerDecisionRequest(decision="approve", actor_role="manager", reason="离线评测进入采购阶段"),
    )
    return container.project_service.procurement_agent_review(
        db,
        project_detail.id,
        ProcurementAgentReviewRequest(
            vendor_name=case.vendor.vendor_name,
            source_platform=case.vendor.source_platform,
            source_url=case.vendor.source_url,
            contact_name=case.vendor.contact_name,
            contact_email=case.vendor.contact_email,
            contact_phone=case.vendor.contact_phone,
            profile_summary=case.vendor.profile_summary,
            procurement_notes=case.vendor.procurement_notes,
            handles_company_data=case.vendor.handles_company_data,
            requires_system_integration=case.vendor.requires_system_integration,
            quoted_amount=case.vendor.quoted_amount,
            focus_points=case.vendor.focus_points,
            user_role="procurement",
            top_k=5,
        ),
        current_user=PROCUREMENT_USER,
    )


def _average(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 3) if scores else 0.0


def _embedding_backend(container: AppContainer) -> str:
    return "sentence_transformer" if container.embedding_service.using_sentence_transformer else "hash_fallback"


def _warm_up_embedding_if_needed(container: AppContainer, pipeline: str) -> None:
    if pipeline != "bm25_only":
        container.embedding_service.embed_text("采购评测语义向量预热")


def _should_print_case_progress(index: int, total: int) -> bool:
    if os.getenv("PROC_EVAL_VERBOSE", "").strip() == "1":
        return True
    return index == 1 or index == total or index % PROGRESS_EVERY == 0


def run_ablation() -> dict[str, object]:
    start_time = time.perf_counter()
    benchmark_mode = (os.getenv("PROC_EVAL_BENCHMARK_MODE") or DEFAULT_BENCHMARK_MODE).strip().lower()
    if benchmark_mode not in {"standard", "hard"}:
        raise ValueError("PROC_EVAL_BENCHMARK_MODE must be 'standard' or 'hard'.")
    scenario_filters = tuple(
        item.strip() for item in (os.getenv("PROC_EVAL_SCENARIOS") or "").split(",") if item.strip()
    )
    case_limit_raw = (os.getenv("PROC_EVAL_CASE_LIMIT") or "").strip()
    case_limit = int(case_limit_raw) if case_limit_raw.isdigit() and int(case_limit_raw) > 0 else 0
    filtered_cases = tuple(
        case for case in PROCUREMENT_REVIEW_EVAL_CASES if not scenario_filters or case.scenario_type in scenario_filters
    )
    cases = tuple(filtered_cases[:case_limit]) if case_limit else filtered_cases
    pipeline_override = tuple(
        item.strip() for item in (os.getenv("PROC_EVAL_PIPELINES") or "").split(",") if item.strip()
    )
    pipelines = pipeline_override or DEFAULT_PIPELINES
    summary: dict[str, object] = {
        "benchmark_version": f"procurement_risk_analysis_v2_{benchmark_mode}",
        "benchmark_mode": benchmark_mode,
        "doc_count": 0,
        "docs": [],
        "case_count": len(cases),
        "scenario_breakdown": dict(Counter(case.scenario_type for case in cases)),
        "embedding_model": EMBEDDING_MODEL_PATH,
        "scenario_filters": list(scenario_filters),
        "pipelines_requested": list(pipelines),
        "pipelines": {},
    }

    for pipeline in pipelines:
        container, db, ingested_docs = ingest_procurement_only()
        if benchmark_mode == "hard":
            _enable_hard_query_mode(container)
        pipeline_start = time.perf_counter()
        _warm_up_embedding_if_needed(container, pipeline)
        print(f"[eval] start pipeline={pipeline} cases={len(cases)}", flush=True)

        required_tag_recall_scores: list[float] = []
        forbidden_tag_violation_scores: list[float] = []
        required_missing_recall_scores: list[float] = []
        forbidden_missing_violation_scores: list[float] = []
        case_success_scores: list[float] = []
        doc_hit1_scores: list[float] = []
        doc_hit5_scores: list[float] = []
        doc_mrr_scores: list[float] = []
        failures: list[dict[str, object]] = []

        summary["doc_count"] = len(ingested_docs)
        summary["docs"] = list(ingested_docs)
        summary["embedding_backend"] = _embedding_backend(container)
        summary["embedding_dimension"] = container.embedding_service.dimensions
        if pipeline != "bm25_only" and summary["embedding_backend"] == "hash_fallback":
            print(
                "[eval][warn] embedding model was not loaded; semantic/RRF metrics are not reliable. "
                f"reason={container.embedding_service.load_error or 'sentence-transformer unavailable'}",
                flush=True,
            )

        cross_encoder_active = False
        try:
            with _override_retrieve(container, pipeline):
                for index, case in enumerate(cases, start=1):
                    if _should_print_case_progress(index, len(cases)):
                        print(
                            f"[eval] pipeline={pipeline} progress={index}/{len(cases)} "
                            f"scenario={case.scenario_type}",
                            flush=True,
                        )
                    try:
                        result = _run_case(container, db, case=case, index=index, pipeline=pipeline)
                    except Exception as exc:  # pragma: no cover - benchmark robustness
                        failures.append(
                            {
                                "case_id": case.case_id,
                                "scenario_type": case.scenario_type,
                                "description": case.description,
                                "error": str(exc),
                            }
                        )
                        required_tag_recall_scores.append(0.0)
                        forbidden_tag_violation_scores.append(1.0)
                        required_missing_recall_scores.append(0.0)
                        forbidden_missing_violation_scores.append(1.0)
                        case_success_scores.append(0.0)
                        doc_hit1_scores.append(0.0)
                        doc_hit5_scores.append(0.0)
                        doc_mrr_scores.append(0.0)
                        continue

                    analysis_tags = list(result.assessment.analysis_tags or [])
                    predicted_missing = list(result.assessment.missing_materials)
                    evidence_titles = [item.document_title for item in result.assessment.evidence]
                    if not evidence_titles:
                        evidence_titles = [item.document_title for item in result.review.citations]
                    retrieval_debug = {}
                    if isinstance(result.review.debug_summary, dict):
                        retrieval_debug = result.review.debug_summary.get("retrieval", {}) or {}
                    cross_encoder_active = bool(cross_encoder_active or retrieval_debug.get("cross_encoder_active", False))

                    expected = _expected_for_mode(case, benchmark_mode)
                    required_tag_recall = _required_recall(
                        analysis_tags,
                        expected.required_analysis_tags,
                    )
                    forbidden_tag_violation = _forbidden_violation(
                        analysis_tags,
                        expected.forbidden_analysis_tags,
                    )
                    required_missing_recall = _required_recall(
                        predicted_missing,
                        expected.required_missing_materials,
                    )
                    forbidden_missing_violation = _forbidden_violation(
                        predicted_missing,
                        expected.forbidden_missing_materials,
                    )
                    doc_hit1, doc_hit5, doc_mrr = _doc_rank_metrics(evidence_titles, expected.acceptable_titles)
                    case_success = _case_success(
                        analysis_tags=analysis_tags,
                        missing_materials=predicted_missing,
                        evidence_titles=evidence_titles,
                        expected=expected,
                    )

                    required_tag_recall_scores.append(required_tag_recall)
                    forbidden_tag_violation_scores.append(forbidden_tag_violation)
                    required_missing_recall_scores.append(required_missing_recall)
                    forbidden_missing_violation_scores.append(forbidden_missing_violation)
                    case_success_scores.append(case_success)
                    doc_hit1_scores.append(doc_hit1)
                    doc_hit5_scores.append(doc_hit5)
                    doc_mrr_scores.append(doc_mrr)

                    if case_success == 0.0:
                        failures.append(
                            {
                                "case_id": case.case_id,
                                "scenario_type": case.scenario_type,
                                "description": case.description,
                                "required_analysis_tags": list(expected.required_analysis_tags),
                                "forbidden_analysis_tags": list(expected.forbidden_analysis_tags),
                                "returned_analysis_tags": analysis_tags,
                                "required_missing_materials": list(expected.required_missing_materials),
                                "forbidden_missing_materials": list(expected.forbidden_missing_materials),
                                "returned_missing_materials": predicted_missing,
                                "acceptable_titles": list(expected.acceptable_titles),
                                "returned_titles": evidence_titles[:5],
                            }
                        )

            summary["pipelines"][pipeline] = {
                "case_success_rate": _average(case_success_scores),
                "required_analysis_tag_recall": _average(required_tag_recall_scores),
                "forbidden_analysis_tag_violation_rate": _average(forbidden_tag_violation_scores),
                "required_missing_materials_recall": _average(required_missing_recall_scores),
                "forbidden_missing_materials_violation_rate": _average(forbidden_missing_violation_scores),
                "supporting_doc_hit@1": _average(doc_hit1_scores),
                "supporting_doc_hit@5": _average(doc_hit5_scores),
                "supporting_doc_mrr": _average(doc_mrr_scores),
                "cross_encoder_active": cross_encoder_active,
                "embedding_backend": _embedding_backend(container),
                "embedding_dimension": container.embedding_service.dimensions,
                "failures": failures[:12],
                "elapsed_seconds": round(time.perf_counter() - pipeline_start, 2),
            }
            print(
                f"[eval] done pipeline={pipeline} "
                f"case_success={summary['pipelines'][pipeline]['case_success_rate']} "
                f"tag_recall={summary['pipelines'][pipeline]['required_analysis_tag_recall']} "
                f"missing_recall={summary['pipelines'][pipeline]['required_missing_materials_recall']} "
                f"doc_hit@1={summary['pipelines'][pipeline]['supporting_doc_hit@1']} "
                f"doc_hit@5={summary['pipelines'][pipeline]['supporting_doc_hit@5']} "
                f"doc_mrr={summary['pipelines'][pipeline]['supporting_doc_mrr']} "
                f"elapsed={summary['pipelines'][pipeline]['elapsed_seconds']}s",
                flush=True,
            )
        finally:
            db.close()

    summary["elapsed_seconds"] = round(time.perf_counter() - start_time, 2)
    return summary


if __name__ == "__main__":
    result = run_ablation()
    out_path = Path.cwd() / "tmp_eval_procurement_ablation" / "ablation_result.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "benchmark_version": result.get("benchmark_version"),
        "benchmark_mode": result.get("benchmark_mode"),
        "case_count": result.get("case_count"),
        "doc_count": result.get("doc_count"),
        "embedding_backend": result.get("embedding_backend"),
        "embedding_dimension": result.get("embedding_dimension"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "pipelines": {
            name: {
                key: metrics.get(key)
                for key in (
                    "case_success_rate",
                    "required_analysis_tag_recall",
                    "forbidden_analysis_tag_violation_rate",
                    "required_missing_materials_recall",
                    "forbidden_missing_materials_violation_rate",
                    "supporting_doc_hit@1",
                    "supporting_doc_hit@5",
                    "supporting_doc_mrr",
                    "cross_encoder_active",
                    "embedding_backend",
                    "embedding_dimension",
                    "elapsed_seconds",
                )
            }
            for name, metrics in dict(result.get("pipelines", {})).items()
        },
    }
    summary_path = out_path.with_name("ablation_summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[eval] compact summary")
    print(f"  result_file: {out_path}")
    print(f"  summary_file: {summary_path}")
    print(
        f"  cases={summary['case_count']} docs={summary['doc_count']} "
        f"mode={summary['benchmark_mode']} "
        f"embedding={summary['embedding_backend']}({summary['embedding_dimension']}) "
        f"elapsed={summary['elapsed_seconds']}s"
    )
    for name, metrics in summary["pipelines"].items():
        print(
            f"  {name}: "
            f"success={metrics['case_success_rate']} "
            f"tag_recall={metrics['required_analysis_tag_recall']} "
            f"missing_recall={metrics['required_missing_materials_recall']} "
            f"doc_hit@1={metrics['supporting_doc_hit@1']} "
            f"doc_hit@5={metrics['supporting_doc_hit@5']} "
            f"doc_mrr={metrics['supporting_doc_mrr']} "
            f"embedding={metrics['embedding_backend']}({metrics['embedding_dimension']}) "
            f"elapsed={metrics['elapsed_seconds']}s"
        )
