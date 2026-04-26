from __future__ import annotations

import statistics
import time
from time import perf_counter

from app.core.config import build_settings, get_settings
from app.main import create_container


CASES = [
    {
        "name": "procurement_supplier_fit",
        "query": "供应商主体信息、数据处理和系统接入能力是否满足当前采购准入要求",
        "user_role": "procurement",
        "top_k": 5,
        "plan": {
            "task_mode": "procurement_fit_review",
            "source_type_hints": ["markdown", "csv"],
            "document_hints": ["采购核心", "供应商准入", "安全评审"],
            "query_variants": ["供应商准入 数据处理 系统接入 安全评审"],
        },
    },
    {
        "name": "legal_contract_review",
        "query": "对方合同将责任上限改成三个月服务费且删除审计权，这种修改是否触碰法务红线",
        "user_role": "legal",
        "top_k": 5,
        "plan": {
            "task_mode": "legal_contract_review",
            "source_type_hints": ["markdown"],
            "document_hints": ["法务核心", "合同审查红线", "标准主服务协议"],
            "query_variants": ["责任上限弱化 审计权缺失 合同红线"],
        },
    },
]


def _run_once(container, case: dict[str, object], nonce: str) -> tuple[float, dict[str, object]]:
    query = str(case["query"])
    user_role = str(case["user_role"])
    top_k = int(case["top_k"])
    plan = dict(case["plan"])
    plan["domain_labels"] = [nonce]
    started = perf_counter()
    with container.session_factory() as db:
        _, debug = container.retrieval_service.retrieve(
            db,
            query=query,
            user_role=user_role,
            top_k=top_k,
            plan=plan,
        )
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    return elapsed_ms, debug


def main() -> None:
    base_settings = get_settings()
    settings = build_settings(
        app_name=base_settings.app_name,
        database_url=base_settings.database_url,
        openai_api_base=base_settings.openai_api_base,
        openai_api_key=base_settings.openai_api_key,
        openai_model=base_settings.openai_model,
        embedding_model=base_settings.embedding_model,
        embedding_device=base_settings.embedding_device,
        reranker_model=base_settings.reranker_model,
        reranker_device=base_settings.reranker_device,
        reranker_enabled=False,
        default_top_k=base_settings.default_top_k,
        redis_url=base_settings.redis_url,
        redis_key_prefix=base_settings.redis_key_prefix,
        retrieval_cache_ttl_seconds=base_settings.retrieval_cache_ttl_seconds,
        storage_dir=str(base_settings.storage_dir),
        api_base_url=base_settings.api_base_url,
    )
    container = create_container(settings)
    retrieval_service = container.retrieval_service
    with container.session_factory() as db:
        document_count = len(retrieval_service.repository.list_documents(db))

    print("[cache-benchmark] start")
    print(
        f"[cache-benchmark] docs={document_count} backend={retrieval_service._active_cache_backend_name()} "
        f"redis_url={'set' if settings.redis_url else 'unset'} ttl={settings.retrieval_cache_ttl_seconds}s "
        f"reranker_enabled={settings.reranker_enabled}"
    )

    cold_samples: list[float] = []
    warm_samples: list[float] = []
    for index, case in enumerate(CASES, start=1):
        nonce = f"bench-{case['name']}-{time.time_ns()}"
        cold_ms, cold_debug = _run_once(container, case, nonce)
        warm_ms, warm_debug = _run_once(container, case, nonce)
        cold_samples.append(cold_ms)
        warm_samples.append(warm_ms)
        speedup = round(cold_ms / max(warm_ms, 1e-6), 2)
        print(
            f"[cache-benchmark] case={index}/{len(CASES)} name={case['name']} "
            f"cold={cold_ms}ms warm={warm_ms}ms speedup={speedup}x "
            f"cache_source={warm_debug.get('cache', {}).get('source')} "
            f"selected={','.join(warm_debug.get('selected_titles', [])[:2])}"
        )
        print(
            f"[cache-benchmark]   cold_stage_ms={cold_debug.get('latency_ms', {})} "
            f"warm_stage_ms={warm_debug.get('latency_ms', {})}"
        )

    avg_cold = round(statistics.mean(cold_samples), 2) if cold_samples else 0.0
    avg_warm = round(statistics.mean(warm_samples), 2) if warm_samples else 0.0
    improvement = round((1 - (avg_warm / max(avg_cold, 1e-6))) * 100, 2) if cold_samples else 0.0
    print("[cache-benchmark] summary")
    print(
        f"[cache-benchmark] avg_cold={avg_cold}ms avg_warm={avg_warm}ms "
        f"latency_reduction={improvement}% cache_stats={retrieval_service.cache_stats()}"
    )


if __name__ == "__main__":
    main()
