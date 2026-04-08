from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_ingestion_service
from app.schemas.knowledge import IndexingTaskRead, KnowledgeSourceRead, KnowledgeUploadResponse, ReindexRequest, ReindexResponse
from app.services.ingestion.service import IngestionService


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/sources", response_model=list[KnowledgeSourceRead])
def list_sources(
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> list[KnowledgeSourceRead]:
    return ingestion_service.list_sources(db)


@router.get("/tasks/{task_id}", response_model=IndexingTaskRead)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> IndexingTaskRead:
    task = ingestion_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Indexing task not found.")
    return task


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def upload_source(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    remote_url: str | None = Form(default=None),
    allowed_roles: str = Form(default="guest,employee,admin"),
    tags: str = Form(default=""),
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> KnowledgeUploadResponse:
    if file is None and not remote_url:
        raise HTTPException(status_code=400, detail="Provide either a file upload or remote_url.")

    if file is not None:
        data = await file.read()
        stored_path = ingestion_service.persist_upload(file.filename, data)
        response = ingestion_service.submit_ingestion(
            db,
            name=file.filename,
            data=data,
            allowed_roles=allowed_roles,
            tags=tags,
            source_path=stored_path,
        )
    else:
        response = ingestion_service.submit_ingestion(
            db,
            name=remote_url or "remote_source",
            data=b"",
            allowed_roles=allowed_roles,
            tags=tags,
            source_path="",
            remote_url=remote_url,
        )

    db.commit()
    if not response.duplicate:
        background_tasks.add_task(ingestion_service.run_indexing_task, response.task_id)
    return response


@router.post("/reindex", response_model=ReindexResponse)
def reindex_sources(
    payload: ReindexRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> ReindexResponse:
    response = ingestion_service.reindex(db, payload.document_ids)
    db.commit()
    for task_id in response.task_ids:
        background_tasks.add_task(ingestion_service.run_indexing_task, task_id)
    return response
