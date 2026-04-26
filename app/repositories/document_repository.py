from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models.entities import Chunk, Document, IndexingTask, IndexingTaskStatus


class DocumentRepository:
    def is_pgvector_enabled(self, db: Session) -> bool:
        if db.bind is None or db.bind.dialect.name != "postgresql":
            return False
        result = db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'chunks' AND column_name = 'embedding_vector'
                """
            )
        ).first()
        return result is not None

    def list_documents(self, db: Session) -> list[Document]:
        statement = select(Document).order_by(Document.updated_at.desc())
        return list(db.scalars(statement))

    def get_documents(self, db: Session, document_ids: Iterable[str]) -> list[Document]:
        statement = select(Document).where(Document.id.in_(list(document_ids)))
        return list(db.scalars(statement))

    def get_document(self, db: Session, document_id: str) -> Document | None:
        return db.get(Document, document_id)

    def get_document_by_sha(self, db: Session, sha256: str) -> Document | None:
        statement = select(Document).where(Document.sha256 == sha256)
        return db.scalar(statement)

    def get_document_by_title(self, db: Session, title: str) -> Document | None:
        statement = select(Document).where(Document.title == title).order_by(Document.updated_at.desc())
        return db.scalar(statement)

    def create_or_update_document_stub(
        self,
        db: Session,
        *,
        title: str,
        source_type: str,
        source_path: str,
        sha256: str,
        allowed_roles: str,
        tags: str,
        status: str,
    ) -> tuple[Document, bool]:
        duplicate = False
        existing_same_sha = self.get_document_by_sha(db, sha256)
        if existing_same_sha is not None:
            existing_same_sha.status = IndexingTaskStatus.indexed.value
            existing_same_sha.parse_status = IndexingTaskStatus.indexed.value
            existing_same_sha.last_error = ""
            db.flush()
            return existing_same_sha, True

        document = self.get_document_by_title(db, title)
        if document is None:
            document = Document(
                title=title,
                source_type=source_type,
                source_path=source_path,
                sha256=sha256,
                allowed_roles=allowed_roles,
                tags=tags,
                parse_status=status,
                status=status,
                version=1,
                last_error="",
            )
            db.add(document)
        else:
            document.source_type = source_type
            document.source_path = source_path
            document.sha256 = sha256
            document.allowed_roles = allowed_roles
            document.tags = tags
            document.parse_status = status
            document.status = status
            document.version = max(document.version, 1) + 1
            document.last_error = ""
        db.flush()
        return document, duplicate

    def finalize_document_index(
        self,
        db: Session,
        *,
        document_id: str,
        chunks: list[dict[str, object]],
        source_type: str,
        source_path: str,
        allowed_roles: str,
        tags: str,
    ) -> Document:
        document = self.get_document(db, document_id)
        if document is None:
            raise ValueError(f"Unknown document id: {document_id}")

        document.source_type = source_type
        document.source_path = source_path
        document.allowed_roles = allowed_roles
        document.tags = tags
        document.status = IndexingTaskStatus.indexed.value
        document.parse_status = IndexingTaskStatus.indexed.value
        document.last_error = ""
        vector_enabled = self.is_pgvector_enabled(db)

        db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        db.flush()

        for order_index, chunk in enumerate(chunks):
            chunk_row = Chunk(
                document_id=document.id,
                order_index=order_index,
                heading=str(chunk.get("heading", "")),
                location=str(chunk.get("location", "")),
                content=str(chunk["content"]),
                keywords=",".join(chunk.get("keywords", [])),
                embedding_json=json.dumps(chunk.get("embedding", [])),
                token_count=int(chunk.get("token_count", 0)),
                metadata_json=json.dumps(chunk.get("metadata", {})),
            )
            db.add(chunk_row)
            db.flush()
            if vector_enabled:
                self._sync_chunk_vector(db, chunk_id=chunk_row.id, embedding=chunk.get("embedding", []))
        return document

    def mark_document_failed(self, db: Session, *, document_id: str, error: str) -> None:
        document = self.get_document(db, document_id)
        if document is None:
            return
        document.status = IndexingTaskStatus.failed.value
        document.parse_status = IndexingTaskStatus.failed.value
        document.last_error = error[:2000]
        db.flush()

    def create_indexing_task(
        self,
        db: Session,
        *,
        document_id: str,
        source_name: str,
        source_type: str,
        source_path: str,
        remote_url: str,
        sha256: str,
        allowed_roles: str,
        tags: str,
        status: str,
        duplicate: bool,
        chunk_count: int = 0,
        last_error: str = "",
    ) -> IndexingTask:
        task = IndexingTask(
            document_id=document_id,
            source_name=source_name,
            source_type=source_type,
            source_path=source_path,
            remote_url=remote_url,
            sha256=sha256,
            allowed_roles=allowed_roles,
            tags=tags,
            status=status,
            duplicate=duplicate,
            chunk_count=chunk_count,
            last_error=last_error,
            completed_at=datetime.utcnow() if status in {IndexingTaskStatus.indexed.value, IndexingTaskStatus.failed.value} else None,
        )
        db.add(task)
        db.flush()
        return task

    def get_indexing_task(self, db: Session, task_id: str) -> IndexingTask | None:
        return db.get(IndexingTask, task_id)

    def update_indexing_task(
        self,
        db: Session,
        *,
        task_id: str,
        status: str,
        chunk_count: int | None = None,
        last_error: str | None = None,
        duplicate: bool | None = None,
    ) -> IndexingTask | None:
        task = self.get_indexing_task(db, task_id)
        if task is None:
            return None
        task.status = status
        if chunk_count is not None:
            task.chunk_count = chunk_count
        if last_error is not None:
            task.last_error = last_error[:2000]
        if duplicate is not None:
            task.duplicate = duplicate
        if status in {IndexingTaskStatus.indexed.value, IndexingTaskStatus.failed.value}:
            task.completed_at = datetime.utcnow()
        db.flush()
        return task

    def delete_documents(self, db: Session, document_ids: Iterable[str]) -> int:
        ids = [document_id for document_id in document_ids if document_id]
        if not ids:
            return 0
        db.execute(delete(Chunk).where(Chunk.document_id.in_(ids)))
        db.execute(delete(IndexingTask).where(IndexingTask.document_id.in_(ids)))
        result = db.execute(delete(Document).where(Document.id.in_(ids)))
        db.flush()
        return int(result.rowcount or 0)

    def fetch_chunks(self, db: Session) -> list[tuple[Chunk, Document]]:
        statement = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.status == IndexingTaskStatus.indexed.value)
            .order_by(Document.updated_at.desc(), Chunk.order_index.asc())
        )
        return list(db.execute(statement).all())

    def fetch_vector_candidates(
        self,
        db: Session,
        *,
        embedding: list[float],
        user_role: str,
        candidate_limit: int,
        allowed_document_ids: list[str] | None = None,
    ) -> list[dict[str, object]]:
        if not self.is_pgvector_enabled(db) or not embedding:
            return []

        allowed_ids = [item for item in (allowed_document_ids or []) if item]
        document_filter = "AND d.id = ANY(CAST(:allowed_document_ids AS text[]))" if allowed_ids else ""

        rows = db.execute(
            text(
                """
                SELECT
                    c.id AS chunk_id,
                    c.document_id AS document_id,
                    d.title AS document_title,
                    d.tags AS document_tags,
                    d.source_type AS source_type,
                    c.location AS location,
                    c.content AS content,
                    c.heading AS heading,
                    1 - (c.embedding_vector <=> CAST(:embedding AS vector)) AS vector_score
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE d.status = :status
                  AND c.embedding_vector IS NOT NULL
                  AND d.allowed_roles LIKE :role_pattern
                  {document_filter}
                ORDER BY c.embedding_vector <=> CAST(:embedding AS vector)
                LIMIT :candidate_limit
                """
                .replace("{document_filter}", document_filter)
            ),
            {
                "embedding": json.dumps(embedding),
                "status": IndexingTaskStatus.indexed.value,
                "role_pattern": f"%{user_role}%",
                "candidate_limit": candidate_limit,
                "allowed_document_ids": allowed_ids,
            },
        ).mappings()
        return [dict(row) for row in rows]

    def _sync_chunk_vector(self, db: Session, *, chunk_id: str, embedding: object) -> None:
        values = [float(value) for value in (embedding or [])]
        if not values:
            return
        db.execute(
            text("UPDATE chunks SET embedding_vector = CAST(:embedding AS vector) WHERE id = :chunk_id"),
            {"embedding": json.dumps(values), "chunk_id": chunk_id},
        )
