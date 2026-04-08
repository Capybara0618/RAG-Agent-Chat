from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source_type: str
    allowed_roles: list[str]
    tags: list[str]
    parse_status: str
    status: str
    version: int
    last_error: str
    updated_at: datetime


class IndexingTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    source_name: str
    source_type: str
    status: str
    duplicate: bool
    chunk_count: int
    last_error: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class KnowledgeUploadResponse(BaseModel):
    task_id: str
    source: KnowledgeSourceRead
    chunk_count: int = 0
    duplicate: bool = False


class ReindexRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)


class ReindexResponse(BaseModel):
    reindexed: int
    failed: int
    skipped: int
    task_ids: list[str] = Field(default_factory=list)
