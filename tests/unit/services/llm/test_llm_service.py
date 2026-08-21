from app.models.llm import LLMRequest
from app.services.llm.interface import ILLMService
from app.services.llm.mock_service import MockLLMService


def test_mock_llm_implements_interface():

    llm = MockLLMService()

    assert isinstance(llm, ILLMService)


async def test_mock_llm_generate():

    llm = MockLLMService()

    request = LLMRequest(
        prompt="What is MyImpact?"
    )

    response = await llm.generate(request)

    assert response.content == (
        "Mock response for: What is MyImpact?"
    )

    assert response.model == "mock-model"