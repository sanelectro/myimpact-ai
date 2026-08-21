from openai import AsyncAzureOpenAI

from app.config.settings import get_settings
from app.services.llm.interface import ILLMService


class AzureAIService(ILLMService):

    def __init__(self):
        settings = get_settings()

        self.client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )

        self.model = settings.azure_openai_deployment

    async def generate(self, prompt: str) -> str:

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        return response.choices[0].message.content or ""