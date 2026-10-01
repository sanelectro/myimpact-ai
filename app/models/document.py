from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentType(str, Enum):
    UNKNOWN = "unknown"
    GOAL = "goal"
    ROLE = "role"
    RESPONSIBILITY = "responsibility"
    ONE_TO_ONE = "one_to_one"
    DEVELOPMENT = "development"
    PERSONAL_EVIDENCE = "personal_evidence"


class DocumentScopeType(str, Enum):
    GLOBAL = "global"
    ROLE = "role"
    EMPLOYEE = "employee"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSED = "processed"
    FAILED = "failed"


class DocumentClassification(BaseModel):
    document_type: DocumentType
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    document_type: DocumentType
    scope_type: DocumentScopeType = DocumentScopeType.EMPLOYEE
    scope_id: str | None = None

    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    storage_path: str = Field(min_length=1)
    extracted_content_path: str | None = None
    classification_type: DocumentType | None = None
    classification_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )
    classification_reason: str | None = None
    classification_error: str | None = None
    classified_at: datetime | None = None

    source: str | None = None
    effective_start: date | None = None
    effective_end: date | None = None
    content_hash: str | None = None
    status: DocumentStatus = DocumentStatus.UPLOADED

    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == DocumentScopeType.GLOBAL:
            if self.scope_id is not None:
                raise ValueError(
                    "Global documents must not have a scope_id."
                )
            return self

        if not self.scope_id:
            raise ValueError(
                f"{self.scope_type.value} documents require a scope_id."
            )

        return self


class DocumentCreate(BaseModel):
    user_id: str
    document_type: DocumentType
    scope_type: DocumentScopeType = DocumentScopeType.EMPLOYEE
    scope_id: str | None = None

    file_name: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    storage_path: str = Field(min_length=1)

    source: str | None = None
    effective_start: date | None = None
    effective_end: date | None = None
    content_hash: str | None = None

    @model_validator(mode="after")
    def normalize_scope(self):
        if self.scope_type == DocumentScopeType.GLOBAL:
            if self.scope_id is not None:
                raise ValueError(
                    "Global documents must not have a scope_id."
                )
            return self

        if self.scope_type == DocumentScopeType.EMPLOYEE:
            if self.scope_id is None:
                self.scope_id = self.user_id
            elif self.scope_id != self.user_id:
                raise ValueError(
                    "Employee document scope_id must match user_id."
                )
            return self

        if not self.scope_id:
            raise ValueError("Role documents require a scope_id.")

        return self
