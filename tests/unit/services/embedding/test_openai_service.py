from unittest.mock import AsyncMock, MagicMock

from app.models.embedding import EmbeddingRequest
from app.services.embedding.openai_service import OpenAIEmbeddingService


async def test_openai_embedding_implements_contract():
    service = OpenAIEmbeddingService.__new__(OpenAIEmbeddingService)
    service.client = MagicMock()
    service.client.embeddings.create = AsyncMock()
    service.model = "text-embedding-test"

    first = MagicMock()
    first.index = 1
    first.embedding = [0.2, 0.3]

    second = MagicMock()
    second.index = 0
    second.embedding = [0.1, 0.4]

    provider_response = MagicMock()
    provider_response.data = [first, second]
    service.client.embeddings.create.return_value = provider_response

    response = await service.embed(
        EmbeddingRequest(inputs=["first", "second"])
    )

    assert response.embeddings == [[0.1, 0.4], [0.2, 0.3]]
    assert response.model == "text-embedding-test"
    service.client.embeddings.create.assert_awaited_once_with(
        model="text-embedding-test",
        input=["first", "second"],
    )
