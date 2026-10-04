from app.models.api_v1_chat import ChatResponse
from app.models.llm import LLMRequest
from app.services.llm.interface import ILLMService


class ChatService:
    """Thin product-level orchestration over the existing LLM abstraction."""

    def __init__(self, llm_service: ILLMService):
        self.llm_service = llm_service

    async def respond(self, message: str) -> ChatResponse:
        response = await self.llm_service.generate(
            request=LLMRequest(prompt=message.strip()),
        )
        return ChatResponse(message=response.content)
