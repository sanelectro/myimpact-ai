import pytest

from app.models.embedding import EmbeddingRequest
from app.services.embedding.mock_service import MockEmbeddingService


def test_mock_embedding_rejects_invalid_dimensions():
    with pytest.raises(ValueError, match="greater than zero"):
        MockEmbeddingService(dimensions=0)


async def test_mock_embedding_vectors_are_normalized():
    service = MockEmbeddingService(dimensions=8)

    response = await service.embed(
        EmbeddingRequest(inputs=["technical leadership"])
    )

    vector = response.embeddings[0]
    norm = sum(value * value for value in vector) ** 0.5

    assert norm == pytest.approx(1.0)
