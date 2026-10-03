from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentChunkEmbedding(BaseModel):
    """Vector representation of a document chunk."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_id: str
    embedding: list[float] = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    embedding_dimensions: int = Field(gt=0)
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchResult(BaseModel):
    """A knowledge chunk returned by semantic retrieval."""

    chunk_id: str
    document_id: str
    content: str
    heading_path: list[str]
    document_type: str
    scope_type: str
    scope_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    similarity: float = Field(ge=-1, le=1)
