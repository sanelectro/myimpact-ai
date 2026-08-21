import pytest

from app.config.settings import get_settings
from app.models.llm import LLMRequest
from app.services.llm.groq_service import GroqLLMService


@pytest.mark.integration
async def test_groq_llm_service():

    settings = get_settings()

    if not settings.groq_api_key:
        pytest.skip("GROQ_API_KEY is not configured")

    llm = GroqLLMService()

    request = LLMRequest(
        prompt="Reply with exactly: MyImpact AI is working"
    )

    response = await llm.generate(request)

    assert response.content
    assert response.model

    print(f"\nModel: {response.model}")
    print(f"Response: {response.content}")