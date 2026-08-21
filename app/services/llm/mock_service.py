from app.models.llm import LLMRequest, LLMResponse
from app.services.llm.interface import ILLMService


class MockLLMService(ILLMService):

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        return LLMResponse(
            content=f"Mock response for: {request.prompt}",
            model="mock-model",
        )