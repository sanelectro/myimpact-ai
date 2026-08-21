from app.config.settings import (
    LLMProvider,
    get_settings,
)
from app.services.llm.azure_service import AzureAIService
from app.services.llm.groq_service import GroqLLMService
from app.services.llm.interface import ILLMService


def create_llm_service() -> ILLMService:

    settings = get_settings()

    if settings.llm_provider == LLMProvider.GROQ:
        return GroqLLMService()

    if settings.llm_provider == LLMProvider.AZURE:
        return AzureAIService()

    raise ValueError(
        f"Unsupported LLM provider: {settings.llm_provider}"
    )