from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    GOAL = "goal"
    ROLE = "role"
    RESPONSIBILITY = "responsibility"
    ONE_TO_ONE = "one_to_one"
    DEVELOPMENT = "development"
    PERSONAL_EVIDENCE = "personal_evidence"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSED = "processed"
    FAILED = "failed"


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    document_type: DocumentType
    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    storage_path: str = Field(min_length=1)
    extracted_text: str | None = None
    source: str | None = None
    effective_start: date | None = None
    effective_end: date | None = None
    content_hash: str | None = None
    status: DocumentStatus = DocumentStatus.UPLOADED
    created_at: datetime
    updated_at: datetime


class DocumentCreate(BaseModel):
    user_id: str
    document_type: DocumentType
    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    storage_path: str = Field(min_length=1)
    source: str | None = None
    effective_start: date | None = None
    effective_end: date | None = None
    content_hash: str | None = None
