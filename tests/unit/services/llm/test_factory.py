from unittest.mock import patch

from app.config.settings import LLMProvider
from app.services.llm.factory import create_llm_service


def test_factory_returns_groq_service():

    with patch(
        "app.services.llm.factory.get_settings"
    ) as mock_settings, patch(
        "app.services.llm.factory.GroqLLMService"
    ) as mock_groq:

        mock_settings.return_value.llm_provider = LLMProvider.GROQ

        service = create_llm_service()

        mock_groq.assert_called_once()
        assert service == mock_groq.return_value


def test_factory_returns_azure_service():

    with patch(
        "app.services.llm.factory.get_settings"
    ) as mock_settings, patch(
        "app.services.llm.factory.AzureAIService"
    ) as mock_azure:

        mock_settings.return_value.llm_provider = LLMProvider.AZURE

        service = create_llm_service()

        mock_azure.assert_called_once()
        assert service == mock_azure.return_value


def test_factory_rejects_unknown_provider():

    with patch(
        "app.services.llm.factory.get_settings"
    ) as mock_settings:

        mock_settings.return_value.llm_provider = "unknown"

        try:
            create_llm_service()
            assert False, "Expected ValueError"

        except ValueError as ex:
            assert "Unsupported LLM provider" in str(ex)