from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BASE_DIR, Settings
from app.core.security import expand_role_scope, normalize_roles
from app.models.entities import IndexingTaskStatus
from app.repositories.document_repository import DocumentRepository
from app.schemas.knowledge import (
    DeleteKnowledgeSourcesResponse,
    IndexingTaskRead,
    KnowledgeSourceRead,
    KnowledgeUploadResponse,
    ProcurementBaselineRebuildResponse,
    ReindexResponse,
)
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
        session_factory: sessionmaker,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.parser = parser
        self.embedding_service = embedding_service
        self.session_factory = session_factory

    def submit_ingestion(
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
        source_type = self.parser.detect_source_type(name, remote_url)
        sha256 = hashlib.sha256(data if data else (remote_url or name).encode("utf-8")).hexdigest()
        role_scope = expand_role_scope(allowed_roles)
        document, duplicate = self.repository.create_or_update_document_stub(
            db,
            title=Path(name).name,
            source_type=source_type,
            source_path=source_path or remote_url or "",
            sha256=sha256,
            allowed_roles=",".join(role_scope),
            tags=tags or "",
            status=IndexingTaskStatus.uploaded.value,
        )
        task = self.repository.create_indexing_task(
            db,
            document_id=document.id,
            source_name=Path(name).name,
            source_type=source_type,
            source_path=source_path or "",
            remote_url=remote_url or "",
            sha256=sha256,
            allowed_roles=",".join(role_scope),
            tags=tags or "",
            status=IndexingTaskStatus.indexed.value if duplicate else IndexingTaskStatus.uploaded.value,
            duplicate=duplicate,
        )
        if duplicate:
            document.status = IndexingTaskStatus.indexed.value
            document.parse_status = IndexingTaskStatus.indexed.value
        return KnowledgeUploadResponse(
            task_id=task.id,
            source=self._to_source_read(document),
            chunk_count=task.chunk_count,
            duplicate=duplicate,
        )

    def run_indexing_task(self, task_id: str) -> None:
        db = self.session_factory()
        try:
            task = self.repository.get_indexing_task(db, task_id)
            if task is None or task.duplicate:
                return

            self.repository.update_indexing_task(db, task_id=task_id, status=IndexingTaskStatus.indexing.value)
            document = self.repository.get_document(db, task.document_id)
            if document is not None:
                document.status = IndexingTaskStatus.indexing.value
                document.parse_status = IndexingTaskStatus.indexing.value
            db.commit()

            if task.remote_url:
                data = b""
                source_type, sections = self.parser.parse_bytes(name=task.source_name, data=data, remote_url=task.remote_url)
            else:
                path = Path(task.source_path)
                data = path.read_bytes()
                source_type, sections = self.parser.parse_bytes(name=task.source_name, data=data, remote_url=None)

            chunks = semantic_chunk_sections(sections)
            for chunk in chunks:
                chunk["embedding"] = self.embedding_service.embed_text(str(chunk["content"]))

            self.repository.finalize_document_index(
                db,
                document_id=task.document_id,
                chunks=chunks,
                source_type=source_type,
                source_path=task.source_path or task.remote_url,
                allowed_roles=task.allowed_roles,
                tags=task.tags,
            )
            self.repository.update_indexing_task(
                db,
                task_id=task_id,
                status=IndexingTaskStatus.indexed.value,
                chunk_count=len(chunks),
                last_error="",
            )
            db.commit()
        except Exception as exc:
            task = self.repository.get_indexing_task(db, task_id)
            if task is not None:
                self.repository.update_indexing_task(
                    db,
                    task_id=task_id,
                    status=IndexingTaskStatus.failed.value,
                    last_error=str(exc),
                )
                if task.document_id:
                    self.repository.mark_document_failed(db, document_id=task.document_id, error=str(exc))
                db.commit()
        finally:
            db.close()

    def persist_upload(self, name: str, data: bytes) -> str:
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        target = self.settings.storage_dir / name
        target.write_bytes(data)
        return str(target)

    def list_sources(self, db: Session) -> list[KnowledgeSourceRead]:
        return [self._to_source_read(document) for document in self.repository.list_documents(db)]

    def get_task(self, db: Session, task_id: str) -> IndexingTaskRead | None:
        task = self.repository.get_indexing_task(db, task_id)
        if task is None:
            return None
        return IndexingTaskRead.model_validate(task)

    def reindex(self, db: Session, document_ids: list[str]) -> ReindexResponse:
        documents = self.repository.get_documents(db, document_ids) if document_ids else self.repository.list_documents(db)
        task_ids: list[str] = []
        for document in documents:
            task = self.repository.create_indexing_task(
                db,
                document_id=document.id,
                source_name=document.title,
                source_type=document.source_type,
                source_path=document.source_path if not document.source_path.startswith("http") else "",
                remote_url=document.source_path if document.source_path.startswith("http") else "",
                sha256=document.sha256,
                allowed_roles=document.allowed_roles,
                tags=document.tags,
                status=IndexingTaskStatus.uploaded.value,
                duplicate=False,
            )
            document.status = IndexingTaskStatus.uploaded.value
            document.parse_status = IndexingTaskStatus.uploaded.value
            document.last_error = ""
            task_ids.append(task.id)
        db.flush()
        return ReindexResponse(reindexed=len(task_ids), failed=0, skipped=0, task_ids=task_ids)

    def delete_sources(self, db: Session, document_ids: list[str]) -> DeleteKnowledgeSourcesResponse:
        documents = self.repository.get_documents(db, document_ids)
        protected: list[str] = []
        removable_ids: list[str] = []

        for document in documents:
            tag_set = {tag.strip() for tag in (document.tags or "").split(",") if tag.strip()}
            if "project_artifact" in tag_set:
                protected.append(document.title)
                continue
            removable_ids.append(document.id)
            self._delete_local_source_file(document.source_path)

        deleted = self.repository.delete_documents(db, removable_ids)
        db.flush()
        return DeleteKnowledgeSourcesResponse(
            deleted=deleted,
            skipped=max(len(document_ids) - deleted, 0),
            protected_titles=protected,
        )

    def rebuild_procurement_baseline(self, db: Session) -> ProcurementBaselineRebuildResponse:
        baseline_files = sorted((BASE_DIR / "data").glob("procurement_cn_*"))
        if not baseline_files:
            raise ValueError("No procurement baseline files found under data directory.")

        existing_documents = self.repository.list_documents(db)
        removed_documents = self.repository.delete_documents(db, [document.id for document in existing_documents])

        task_ids: list[str] = []
        retained_titles: list[str] = []
        for path in baseline_files:
            response = self.submit_ingestion(
                db,
                name=path.name,
                data=path.read_bytes(),
                allowed_roles="employee",
                tags="baseline,procurement",
                source_path=str(path),
            )
            task_ids.append(response.task_id)
            retained_titles.append(path.name)

        return ProcurementBaselineRebuildResponse(
            removed_documents=removed_documents,
            uploaded_documents=len(retained_titles),
            task_ids=task_ids,
            retained_titles=retained_titles,
        )

    def _to_source_read(self, document) -> KnowledgeSourceRead:
        return KnowledgeSourceRead(
            id=document.id,
            title=document.title,
            source_type=document.source_type,
            allowed_roles=normalize_roles(document.allowed_roles.split(",")),
            tags=[tag for tag in document.tags.split(",") if tag],
            parse_status=document.parse_status,
            status=document.status,
            version=document.version,
            last_error=document.last_error or "",
            updated_at=document.updated_at,
        )

    def _delete_local_source_file(self, source_path: str) -> None:
        normalized = (source_path or "").strip()
        if not normalized or normalized.startswith("http"):
            return
        try:
            path = Path(normalized).resolve()
        except OSError:
            return
        storage_root = self.settings.storage_dir.resolve()
        data_root = (BASE_DIR / "data").resolve()
        if not path.exists() or not path.is_file():
            return
        if storage_root in path.parents or data_root in path.parents:
            try:
                path.unlink()
            except OSError:
                return
