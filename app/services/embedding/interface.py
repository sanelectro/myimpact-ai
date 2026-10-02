from abc import ABC, abstractmethod

from app.models.embedding import EmbeddingRequest, EmbeddingResponse


class IEmbeddingService(ABC):
    """Provider-neutral contract for generating text embeddings."""

    @abstractmethod
    async def embed(
        self,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        pass
