from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.models.embedding import EmbeddingRequest, EmbeddingResponse
from app.services.embedding.interface import IEmbeddingService


class OpenAIEmbeddingService(IEmbeddingService):
    """Embedding provider backed by the OpenAI embeddings API."""

    def __init__(self):
        settings = get_settings()

        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.model = settings.openai_embedding_model

    async def embed(
        self,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        response = await self.client.embeddings.create(
            model=self.model,
            input=request.inputs,
        )

        embeddings = [
            item.embedding
            for item in sorted(response.data, key=lambda item: item.index)
        ]

        return EmbeddingResponse(
            embeddings=embeddings,
            model=self.model,
        )
