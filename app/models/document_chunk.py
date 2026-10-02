from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentScopeType, DocumentType


class DocumentChunk(BaseModel):
    """A canonical piece of document knowledge.

    A chunk is an internal knowledge representation. It is intentionally
    independent of embeddings and vector storage so that those concerns can
    evolve without changing the chunk contract.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    chunk_index: int = Field(ge=0)

    content: str = Field(min_length=1)
    heading_path: list[str] = Field(default_factory=list)

    document_type: DocumentType
    scope_type: DocumentScopeType
    scope_id: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime
    updated_at: datetime