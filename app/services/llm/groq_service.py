from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.models.llm import LLMRequest, LLMResponse
from app.services.llm.interface import ILLMService


class GroqLLMService(ILLMService):

    def __init__(self):

        settings = get_settings()

        self.client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
        )

        self.model = settings.groq_model

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": request.prompt,
                }
            ],
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=self.model,
        )