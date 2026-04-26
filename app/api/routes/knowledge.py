from __future__ import annotations

import asyncio
import json
from queue import Empty, Queue

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_auth_service, get_db, get_ingestion_service, require_roles
from app.schemas.auth import UserProfileRead
from app.schemas.knowledge import (
    DeleteKnowledgeSourcesRequest,
    DeleteKnowledgeSourcesResponse,
    IndexingTaskRead,
    KnowledgeSourceRead,
    KnowledgeUploadResponse,
    ProcurementBaselineRebuildResponse,
    ReindexRequest,
    ReindexResponse,
)
from app.services.auth_service import AuthService
from app.services.ingestion.service import IngestionService


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _require_admin_stream_user(db: Session, auth_service: AuthService, token: str) -> UserProfileRead:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    current_user = auth_service.get_user_by_token(db, token)
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有访问权限。")
    return current_user


def _format_sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/sources", response_model=list[KnowledgeSourceRead])
def list_sources(
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> list[KnowledgeSourceRead]:
    return ingestion_service.list_sources(db)


@router.get("/tasks/{task_id}", response_model=IndexingTaskRead)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> IndexingTaskRead:
    task = ingestion_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Indexing task not found.")
    return task


@router.get("/tasks/{task_id}/stream")
async def stream_task(
    task_id: str,
    token: str = Query(default=""),
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> StreamingResponse:
    _require_admin_stream_user(db, auth_service, token)
    task = ingestion_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Indexing task not found.")

    async def event_generator():
        subscriber: Queue[dict[str, object]] = ingestion_service.subscribe_task_events(task_id)
        try:
            yield _format_sse(
                "task",
                {
                    "event": "task_snapshot",
                    "message": "已连接实时任务流。",
                    "stage": task.status,
                    "task": task.model_dump(mode="json"),
                    "progress": {},
                },
            )
            while True:
                try:
                    payload = await asyncio.to_thread(subscriber.get, True, 15.0)
                except Empty:
                    yield ": ping\n\n"
                    continue
                yield _format_sse("task", payload)
                task_payload = payload.get("task", {})
                if isinstance(task_payload, dict) and task_payload.get("status") in {"indexed", "failed"}:
                    break
        finally:
            ingestion_service.unsubscribe_task_events(task_id, subscriber)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def upload_source(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    remote_url: str | None = Form(default=None),
    allowed_roles: str = Form(default="guest,employee,admin"),
    tags: str = Form(default=""),
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    _: UserProfileRead = Depends(require_roles("admin")),
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


@router.post("/delete", response_model=DeleteKnowledgeSourcesResponse)
def delete_sources(
    payload: DeleteKnowledgeSourcesRequest,
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> DeleteKnowledgeSourcesResponse:
    if not payload.document_ids:
        raise HTTPException(status_code=400, detail="Please provide at least one document id.")
    response = ingestion_service.delete_sources(db, payload.document_ids)
    db.commit()
    return response


@router.post("/reindex", response_model=ReindexResponse)
def reindex_sources(
    payload: ReindexRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> ReindexResponse:
    response = ingestion_service.reindex(db, payload.document_ids)
    db.commit()
    for task_id in response.task_ids:
        background_tasks.add_task(ingestion_service.run_indexing_task, task_id)
    return response


@router.post("/procurement-baseline/rebuild", response_model=ProcurementBaselineRebuildResponse)
def rebuild_procurement_baseline(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    _: UserProfileRead = Depends(require_roles("admin")),
) -> ProcurementBaselineRebuildResponse:
    response = ingestion_service.rebuild_procurement_baseline(db)
    db.commit()
    for task_id in response.task_ids:
        background_tasks.add_task(ingestion_service.run_indexing_task, task_id)
    return response
