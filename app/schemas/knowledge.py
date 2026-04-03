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
    updated_at: datetime


class KnowledgeUploadResponse(BaseModel):
    source: KnowledgeSourceRead
    chunk_count: int
    duplicate: bool = False


class ReindexRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)


class ReindexResponse(BaseModel):
    reindexed: int
    failed: int
    skipped: int