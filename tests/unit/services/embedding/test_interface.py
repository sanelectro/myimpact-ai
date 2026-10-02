from app.models.embedding import EmbeddingRequest
from app.services.embedding.interface import IEmbeddingService
from app.services.embedding.mock_service import MockEmbeddingService


async def test_mock_embedding_implements_interface():
    service = MockEmbeddingService()

    assert isinstance(service, IEmbeddingService)


async def test_mock_embedding_is_deterministic_and_batched():
    service = MockEmbeddingService(dimensions=4)

    request = EmbeddingRequest(inputs=["architecture", "mentoring"])
    response = await service.embed(request)
    repeated = await service.embed(request)

    assert len(response.embeddings) == 2
    assert all(len(vector) == 4 for vector in response.embeddings)
    assert response.embeddings == repeated.embeddings
    assert response.model == "mock-embedding"
