from __future__ import annotations

import json
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import Chunk, Document


class DocumentRepository:
    def list_documents(self, db: Session) -> list[Document]:
        statement = select(Document).order_by(Document.updated_at.desc())
        return list(db.scalars(statement))

    def get_documents(self, db: Session, document_ids: Iterable[str]) -> list[Document]:
        statement = select(Document).where(Document.id.in_(list(document_ids)))
        return list(db.scalars(statement))

    def get_document_by_sha(self, db: Session, sha256: str) -> Document | None:
        statement = select(Document).where(Document.sha256 == sha256)
        return db.scalar(statement)

    def upsert_document_with_chunks(
        self,
        db: Session,
        *,
        title: str,
        source_type: str,
        source_path: str,
        sha256: str,
        allowed_roles: str,
        tags: str,
        chunks: list[dict[str, object]],
    ) -> tuple[Document, bool]:
        document = self.get_document_by_sha(db, sha256)
        is_duplicate = document is not None

        if document is None:
            document = Document(
                title=title,
                source_type=source_type,
                source_path=source_path,
                sha256=sha256,
                allowed_roles=allowed_roles,
                tags=tags,
                parse_status="indexed",
            )
            db.add(document)
            db.flush()
        else:
            document.title = title
            document.source_type = source_type
            document.source_path = source_path
            document.allowed_roles = allowed_roles
            document.tags = tags
            document.parse_status = "indexed"
            db.execute(delete(Chunk).where(Chunk.document_id == document.id))
            db.flush()

        for order_index, chunk in enumerate(chunks):
            db.add(
                Chunk(
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
            )

        db.flush()
        return document, is_duplicate

    def fetch_chunks(self, db: Session) -> list[tuple[Chunk, Document]]:
        statement = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .order_by(Document.updated_at.desc(), Chunk.order_index.asc())
        )
        return list(db.execute(statement).all())