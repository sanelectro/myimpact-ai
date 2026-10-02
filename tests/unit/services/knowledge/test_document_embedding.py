from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.embedding import EmbeddingResponse
from app.services.knowledge.document_embedding import DocumentChunkEmbeddingService


@pytest.mark.asyncio
async def test_embed_document_generates_and_persists_one_vector_per_chunk():
    session = MagicMock()
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(
        return_value=EmbeddingResponse(
            embeddings=[[1.0, 0.0], [0.0, 1.0]],
            model="test-model",
        )
    )

    service = DocumentChunkEmbeddingService(session, embedding_service)
    service.chunk_repository = MagicMock()
    service.embedding_repository = MagicMock()

    chunk_1 = MagicMock(id="chunk-1", content="architecture")
    chunk_2 = MagicMock(id="chunk-2", content="mentoring")
    service.chunk_repository.get_by_document_id.return_value = [
        chunk_1,
        chunk_2,
    ]

    count = await service.embed_document("document-1")

    assert count == 2
    request = embedding_service.embed.await_args.args[0]
    assert request.inputs == ["architecture", "mentoring"]

    assert service.embedding_repository.upsert.call_count == 2
    service.embedding_repository.upsert.assert_any_call(
        chunk_id="chunk-1",
        embedding=[1.0, 0.0],
        embedding_model="test-model",
    )
    service.embedding_repository.upsert.assert_any_call(
        chunk_id="chunk-2",
        embedding=[0.0, 1.0],
        embedding_model="test-model",
    )
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_embed_document_keeps_existing_state_when_provider_fails():
    session = MagicMock()
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(side_effect=RuntimeError("provider"))

    service = DocumentChunkEmbeddingService(session, embedding_service)
    service.chunk_repository = MagicMock()
    service.embedding_repository = MagicMock()
    service.chunk_repository.get_by_document_id.return_value = [
        MagicMock(id="chunk-1", content="architecture")
    ]

    with pytest.raises(RuntimeError, match="provider"):
        await service.embed_document("document-1")

    service.embedding_repository.upsert.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
