from unittest.mock import AsyncMock, MagicMock

from app.models.embedding import EmbeddingRequest
from app.services.embedding.azure_service import AzureEmbeddingService


async def test_azure_embedding_implements_contract():
    service = AzureEmbeddingService.__new__(AzureEmbeddingService)
    service.client = MagicMock()
    service.client.embeddings.create = AsyncMock()
    service.model = "azure-embedding-test"

    item = MagicMock()
    item.index = 0
    item.embedding = [0.5, 0.6]

    provider_response = MagicMock()
    provider_response.data = [item]
    service.client.embeddings.create.return_value = provider_response

    response = await service.embed(
        EmbeddingRequest(inputs=["architecture"])
    )

    assert response.embeddings == [[0.5, 0.6]]
    assert response.model == "azure-embedding-test"
    service.client.embeddings.create.assert_awaited_once_with(
        model="azure-embedding-test",
        input=["architecture"],
    )
