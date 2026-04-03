from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import expand_role_scope, normalize_roles
from app.repositories.document_repository import DocumentRepository
from app.schemas.knowledge import KnowledgeSourceRead, KnowledgeUploadResponse, ReindexResponse
from app.services.ingestion.chunking import semantic_chunk_sections
from app.services.ingestion.connectors import DocumentParser
from app.services.retrieval.embeddings import EmbeddingService


class IngestionService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: DocumentRepository,
        parser: DocumentParser,
        embedding_service: EmbeddingService,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.parser = parser
        self.embedding_service = embedding_service

    def ingest_bytes(
        self,
        db: Session,
        *,
        name: str,
        data: bytes,
        allowed_roles: str | list[str] | None = None,
        tags: str | None = None,
        source_path: str = "",
        remote_url: str | None = None,
    ) -> KnowledgeUploadResponse:
        source_type, sections = self.parser.parse_bytes(name=name, data=data, remote_url=remote_url)
        chunks = semantic_chunk_sections(sections)
        for chunk in chunks:
            chunk["embedding"] = self.embedding_service.embed_text(str(chunk["content"]))
        sha256 = hashlib.sha256(data if data else (remote_url or name).encode("utf-8")).hexdigest()
        role_scope = expand_role_scope(allowed_roles)
        document, duplicate = self.repository.upsert_document_with_chunks(
            db,
            title=Path(name).name,
            source_type=source_type,
            source_path=source_path or remote_url or "",
            sha256=sha256,
            allowed_roles=",".join(role_scope),
            tags=tags or "",
            chunks=chunks,
        )
        return KnowledgeUploadResponse(
            source=KnowledgeSourceRead(
                id=document.id,
                title=document.title,
                source_type=document.source_type,
                allowed_roles=normalize_roles(document.allowed_roles.split(",")),
                tags=[tag for tag in document.tags.split(",") if tag],
                parse_status=document.parse_status,
                updated_at=document.updated_at,
            ),
            chunk_count=len(chunks),
            duplicate=duplicate,
        )

    def persist_upload(self, name: str, data: bytes) -> str:
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        target = self.settings.storage_dir / name
        target.write_bytes(data)
        return str(target)

    def list_sources(self, db: Session) -> list[KnowledgeSourceRead]:
        sources = []
        for document in self.repository.list_documents(db):
            sources.append(
                KnowledgeSourceRead(
                    id=document.id,
                    title=document.title,
                    source_type=document.source_type,
                    allowed_roles=normalize_roles(document.allowed_roles.split(",")),
                    tags=[tag for tag in document.tags.split(",") if tag],
                    parse_status=document.parse_status,
                    updated_at=document.updated_at,
                )
            )
        return sources

    def reindex(self, db: Session, document_ids: list[str]) -> ReindexResponse:
        documents = self.repository.get_documents(db, document_ids) if document_ids else self.repository.list_documents(db)
        reindexed = 0
        failed = 0
        skipped = 0

        for document in documents:
            try:
                if document.source_path.startswith("http"):
                    self.ingest_bytes(
                        db,
                        name=document.title,
                        data=b"",
                        allowed_roles=document.allowed_roles.split(","),
                        tags=document.tags,
                        source_path=document.source_path,
                        remote_url=document.source_path,
                    )
                    reindexed += 1
                    continue

                path = Path(document.source_path)
                if not path.exists():
                    skipped += 1
                    continue

                self.ingest_bytes(
                    db,
                    name=document.title,
                    data=path.read_bytes(),
                    allowed_roles=document.allowed_roles.split(","),
                    tags=document.tags,
                    source_path=str(path),
                )
                reindexed += 1
            except Exception:
                failed += 1
        return ReindexResponse(reindexed=reindexed, failed=failed, skipped=skipped)