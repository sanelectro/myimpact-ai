from pydantic import BaseModel, Field

from app.models.document import DocumentScopeType, DocumentStatus, DocumentType


class KnowledgeDocumentResponse(BaseModel):
    id: str
    file_name: str
    content_type: str
    document_type: DocumentType
    scope_type: DocumentScopeType
    scope_id: str | None = None
    status: DocumentStatus
    classification_type: DocumentType | None = None
    classification_confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: str
    updated_at: str


class KnowledgeRetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    document_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeResult(BaseModel):
    document_id: str
    content: str
    heading_path: list[str]
    document_type: str
    scope_type: str
    scope_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class KnowledgeRetrievalResponse(BaseModel):
    results: list[KnowledgeResult]
