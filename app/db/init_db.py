from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.models.base import Base


RUNTIME_COLUMN_PATCHES: dict[str, dict[str, str]] = {
    "documents": {
        "status": "VARCHAR(50) DEFAULT 'uploaded'",
        "version": "INTEGER DEFAULT 1",
        "last_error": "TEXT DEFAULT ''",
    },
    "trace_records": {
        "debug_summary_json": "TEXT DEFAULT '{}'",
    },
    "eval_cases": {
        "knowledge_domain": "VARCHAR(100) DEFAULT 'general'",
    },
    "eval_runs": {
        "failure_tag_counts_json": "TEXT DEFAULT '{}'",
        "filters_json": "TEXT DEFAULT '{}'",
    },
    "eval_results": {
        "returned_action": "VARCHAR(50) DEFAULT 'answer'",
        "failure_tag": "VARCHAR(80) DEFAULT ''",
        "trace_id": "VARCHAR(36) DEFAULT ''",
    },
    "feedback": {
        "review_status": "VARCHAR(50) DEFAULT 'pending'",
        "candidate_case_json": "TEXT DEFAULT '{}'",
    },
}


def init_db(session_factory: sessionmaker) -> None:
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(bind=engine)
    _ensure_pgvector_runtime(engine)
    _ensure_runtime_columns(engine)
    _ensure_pgvector_index(engine)


def _ensure_runtime_columns(engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, columns in RUNTIME_COLUMN_PATCHES.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name in existing_columns:
                    continue
                connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _ensure_pgvector_runtime(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        chunk_columns = {
            row["column_name"]
            for row in connection.exec_driver_sql(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'chunks'
                """
            ).mappings()
        }
        if "embedding_vector" not in chunk_columns:
            connection.exec_driver_sql("ALTER TABLE chunks ADD COLUMN embedding_vector vector(48)")
        connection.exec_driver_sql(
            """
            UPDATE chunks
            SET embedding_vector = CAST(embedding_json AS vector)
            WHERE embedding_vector IS NULL
              AND embedding_json IS NOT NULL
              AND embedding_json <> '[]'
            """
        )


def _ensure_pgvector_index(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding_vector_hnsw
            ON chunks
            USING hnsw (embedding_vector vector_cosine_ops)
            """
        )
