from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    """Text payload submitted to an embedding provider.

    The request supports batching because document ingestion will normally
    embed several chunks at once.
    """

    inputs: list[str] = Field(min_length=1)


class EmbeddingResponse(BaseModel):
    """Provider-neutral embedding response."""

    embeddings: list[list[float]]
    model: str | None = None
