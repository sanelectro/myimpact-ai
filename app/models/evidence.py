from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EvidenceSourceType(str, Enum):
    JIRA = "jira"
    GITHUB = "github"
    CONFLUENCE = "confluence"
    WORKDAY = "workday"
    PERSONAL = "personal"
    DOCUMENT = "document"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Evidence(BaseModel):
    id: str
    user_id: str
    source_type: EvidenceSourceType
    source_id: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    source_url: str | None = None
    captured_at: datetime
    source_updated_at: datetime | None = None
    content_hash: str | None = None
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


class EvidenceCreate(BaseModel):
    user_id: str
    source_type: EvidenceSourceType
    source_id: str | None = None
    title: str = Field(min_length=1)
    description: str | None = None
    source_url: str | None = None
    captured_at: datetime
    source_updated_at: datetime | None = None
    content_hash: str | None = None
