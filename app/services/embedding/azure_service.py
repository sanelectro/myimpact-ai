from openai import AsyncAzureOpenAI

from app.config.settings import get_settings
from app.models.embedding import EmbeddingRequest, EmbeddingResponse
from app.services.embedding.interface import IEmbeddingService


class AzureEmbeddingService(IEmbeddingService):
    """Embedding provider backed by Azure OpenAI embeddings."""

    def __init__(self):
        settings = get_settings()

        self.client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        self.model = settings.azure_openai_embedding_deployment

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
