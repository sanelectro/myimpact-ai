from abc import ABC, abstractmethod

from app.models.llm import LLMRequest, LLMResponse


class ILLMService(ABC):

    @abstractmethod
    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        pass