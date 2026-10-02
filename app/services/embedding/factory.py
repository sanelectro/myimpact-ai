from app.config.settings import EmbeddingProvider, get_settings
from app.services.embedding.azure_service import AzureEmbeddingService
from app.services.embedding.interface import IEmbeddingService
from app.services.embedding.mock_service import MockEmbeddingService
from app.services.embedding.openai_service import OpenAIEmbeddingService


def create_embedding_service() -> IEmbeddingService:
    settings = get_settings()
    provider = settings.embedding_provider

    if provider == EmbeddingProvider.OPENAI:
        return OpenAIEmbeddingService()

    if provider == EmbeddingProvider.AZURE:
        return AzureEmbeddingService()

    if provider == EmbeddingProvider.MOCK:
        return MockEmbeddingService()

    raise ValueError(f"Unsupported embedding provider: {provider}")
