from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.models.base import Base


RUNTIME_COLUMN_PATCHES: dict[str, dict[str, str]] = {
    "procurement_projects": {
        "created_by_user_id": "VARCHAR(36) DEFAULT ''",
        "selected_vendor_id": "VARCHAR(36) DEFAULT ''",
        "business_value": "TEXT DEFAULT ''",
        "target_go_live_date": "VARCHAR(20) DEFAULT ''",
        "procurement_materials_json": "TEXT DEFAULT '{}'",
    },
    "project_stage_records": {
        "from_stage": "VARCHAR(50) DEFAULT ''",
        "to_stage": "VARCHAR(50) DEFAULT ''",
        "action": "VARCHAR(50) DEFAULT 'entered'",
        "actor_role": "VARCHAR(50) DEFAULT 'system'",
        "reason": "TEXT DEFAULT ''",
    },
    "project_artifacts": {
        "linked_vendor_id": "VARCHAR(36) DEFAULT ''",
        "direction": "VARCHAR(30) DEFAULT 'internal'",
        "version_no": "INTEGER DEFAULT 1",
    },
    "project_decisions": {
        "subject_type": "VARCHAR(50) DEFAULT 'project'",
        "subject_id": "VARCHAR(36) DEFAULT ''",
        "ai_recommendation": "VARCHAR(50) DEFAULT ''",
        "manual_decision": "VARCHAR(50) DEFAULT ''",
        "structured_summary_json": "TEXT DEFAULT '{}'",
        "reason": "TEXT DEFAULT ''",
    },
    "vendor_candidates": {
        "ai_review_json": "TEXT DEFAULT '{}'",
        "contact_name": "VARCHAR(120) DEFAULT ''",
        "contact_email": "VARCHAR(255) DEFAULT ''",
        "contact_phone": "VARCHAR(80) DEFAULT ''",
        "handles_company_data": "BOOLEAN DEFAULT FALSE",
        "requires_system_integration": "BOOLEAN DEFAULT FALSE",
        "quoted_amount": "FLOAT DEFAULT 0",
    },
    "project_risks": {
        "linked_vendor_id": "VARCHAR(36) DEFAULT ''",
    },
    "documents": {
        "status": "VARCHAR(50) DEFAULT 'uploaded'",
        "version": "INTEGER DEFAULT 1",
        "last_error": "TEXT DEFAULT ''",
    },
    "trace_records": {
        "user_id": "VARCHAR(36) DEFAULT ''",
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
        "user_id": "VARCHAR(36) DEFAULT ''",
        "review_status": "VARCHAR(50) DEFAULT 'pending'",
        "candidate_case_json": "TEXT DEFAULT '{}'",
    },
    "chat_sessions": {
        "user_id": "VARCHAR(36) DEFAULT ''",
    },
}


def init_db(session_factory: sessionmaker) -> None:
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(bind=engine)
    _ensure_pgvector_runtime(engine)
    _ensure_runtime_columns(engine)
    _normalize_legacy_procurement_stages(engine)
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


def _normalize_legacy_procurement_stages(engine) -> None:
    stage_mapping = {
        "draft": "business_draft",
        "vendor_onboarding": "manager_review",
        "security_review": "procurement_sourcing",
        "approval": "signing",
    }
    owner_mapping = {
        "business": "business",
        "manager": "manager",
        "procurement": "procurement",
        "legal": "legal",
        "executive": "manager",
        "operations": "admin",
    }

    with engine.begin() as connection:
        for old_stage, new_stage in stage_mapping.items():
            connection.exec_driver_sql(
                f"UPDATE procurement_projects SET current_stage = '{new_stage}' WHERE current_stage = '{old_stage}'"
            )
            for table_name in ("project_tasks", "project_artifacts", "project_decisions", "project_risks", "project_stage_records"):
                connection.exec_driver_sql(
                    f"UPDATE {table_name} SET stage = '{new_stage}' WHERE stage = '{old_stage}'"
                )
            connection.exec_driver_sql(
                f"UPDATE project_stage_records SET from_stage = '{new_stage}' WHERE from_stage = '{old_stage}'"
            )
            connection.exec_driver_sql(
                f"UPDATE project_stage_records SET to_stage = '{new_stage}' WHERE to_stage = '{old_stage}'"
            )

        for owner_role, normalized_role in owner_mapping.items():
            connection.exec_driver_sql(
                f"UPDATE procurement_projects SET current_owner_role = '{normalized_role}' WHERE current_owner_role = '{owner_role}'"
            )
            connection.exec_driver_sql(
                f"UPDATE project_stage_records SET owner_role = '{normalized_role}' WHERE owner_role = '{owner_role}'"
            )
            connection.exec_driver_sql(
                f"UPDATE project_stage_records SET actor_role = '{normalized_role}' WHERE actor_role = '{owner_role}'"
            )
