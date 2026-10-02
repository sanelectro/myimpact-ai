from unittest.mock import patch

from app.config.settings import EmbeddingProvider
from app.services.embedding.azure_service import AzureEmbeddingService
from app.services.embedding.factory import create_embedding_service
from app.services.embedding.mock_service import MockEmbeddingService
from app.services.embedding.openai_service import OpenAIEmbeddingService


def test_factory_returns_openai_service():
    with patch("app.services.embedding.openai_service.AsyncOpenAI"), \
         patch("app.services.embedding.factory.get_settings") as mock_settings:
        mock_settings.return_value.embedding_provider = EmbeddingProvider.OPENAI
        service = create_embedding_service()

    assert isinstance(service, OpenAIEmbeddingService)


def test_factory_returns_azure_service():
    with patch("app.services.embedding.azure_service.AsyncAzureOpenAI"), \
         patch("app.services.embedding.factory.get_settings") as mock_settings:
        mock_settings.return_value.embedding_provider = EmbeddingProvider.AZURE
        service = create_embedding_service()

    assert isinstance(service, AzureEmbeddingService)


def test_factory_returns_mock_service():
    with patch("app.services.embedding.factory.get_settings") as mock_settings:
        mock_settings.return_value.embedding_provider = EmbeddingProvider.MOCK
        service = create_embedding_service()

    assert isinstance(service, MockEmbeddingService)


def test_factory_rejects_unknown_provider():
    with patch("app.services.embedding.factory.get_settings") as mock_settings:
        mock_settings.return_value.embedding_provider = "unknown"

        try:
            create_embedding_service()
            assert False, "Expected ValueError"
        except ValueError as ex:
            assert "Unsupported embedding provider" in str(ex)
