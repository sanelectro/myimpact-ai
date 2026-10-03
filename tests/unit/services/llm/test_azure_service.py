from unittest.mock import AsyncMock, MagicMock

from app.models.llm import LLMRequest
from app.services.llm.azure_service import AzureAIService


async def test_generate_implements_llm_contract():
    service = AzureAIService.__new__(AzureAIService)
    service.client = MagicMock()
    service.client.chat.completions.create = AsyncMock()
    service.model = "azure-test-model"

    provider_response = MagicMock()
    provider_response.choices[0].message.content = "classified response"
    service.client.chat.completions.create.return_value = provider_response

    response = await service.generate(
        LLMRequest(prompt="Classify this document")
    )

    assert response.content == "classified response"
    assert response.model == "azure-test-model"
    service.client.chat.completions.create.assert_awaited_once_with(
        model="azure-test-model",
        messages=[
            {
                "role": "user",
                "content": "Classify this document",
            }
        ],
    )