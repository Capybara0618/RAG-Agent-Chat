from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    openai_api_base: str
    openai_api_key: str
    openai_model: str
    embedding_model: str
    embedding_device: str
    reranker_model: str
    reranker_device: str
    reranker_enabled: bool
    default_top_k: int
    redis_url: str
    redis_key_prefix: str
    retrieval_cache_ttl_seconds: int
    storage_dir: Path
    api_base_url: str


def build_settings(**overrides: object) -> Settings:
    storage_value = overrides.get("storage_dir") or os.getenv("STORAGE_DIR", "data/uploads")
    storage_dir = Path(storage_value)
    if not storage_dir.is_absolute():
        storage_dir = BASE_DIR / storage_dir

    return Settings(
        app_name=str(overrides.get("app_name") or os.getenv("APP_NAME", "KnowledgeOps Copilot")),
        database_url=str(
            overrides.get("database_url")
            or os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/knowledgeops")
        ),
        openai_api_base=str(overrides.get("openai_api_base") or os.getenv("OPENAI_API_BASE", "")),
        openai_api_key=str(overrides.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")),
        openai_model=str(overrides.get("openai_model") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
        embedding_model=str(overrides.get("embedding_model") or os.getenv("EMBEDDING_MODEL", "")),
        embedding_device=str(overrides.get("embedding_device") or os.getenv("EMBEDDING_DEVICE", "cpu")),
        reranker_model=str(overrides.get("reranker_model") or os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")),
        reranker_device=str(overrides.get("reranker_device") or os.getenv("RERANKER_DEVICE", "cpu")),
        reranker_enabled=str(overrides.get("reranker_enabled") or os.getenv("RERANKER_ENABLED", "true")).lower()
        in {"1", "true", "yes", "on"},
        default_top_k=int(overrides.get("default_top_k") or os.getenv("DEFAULT_TOP_K", "5")),
        redis_url=str(overrides.get("redis_url") or os.getenv("REDIS_URL", "")),
        redis_key_prefix=str(
            overrides.get("redis_key_prefix") or os.getenv("REDIS_KEY_PREFIX", "knowledgeops:retrieval:")
        ),
        retrieval_cache_ttl_seconds=int(
            overrides.get("retrieval_cache_ttl_seconds") or os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "120")
        ),
        storage_dir=storage_dir,
        api_base_url=str(overrides.get("api_base_url") or os.getenv("API_BASE_URL", "http://localhost:8000")),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return build_settings()
