from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.models.embedding import EmbeddingResponse
from app.services.knowledge.semantic_retrieval import SemanticRetrievalService


@pytest.mark.asyncio
async def test_semantic_retrieval_generates_query_embedding_and_maps_results():
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(
        return_value=EmbeddingResponse(
            embeddings=[[1.0, 0.0]],
            model="test-model",
        )
    )

    chunk = MagicMock()
    chunk.id = "chunk-1"
    chunk.document_id = "document-1"
    chunk.content = "Drive architecture decisions."
    chunk.heading_path = ["Technical Leadership", "Architecture"]
    chunk.document_type.value = "role"
    chunk.scope_type.value = "employee"
    chunk.scope_id = "user-1"
    chunk.metadata_ = {"source_page": 3}

    repository = MagicMock()
    repository.search_similar.return_value = [(chunk, 0.97)]

    service = SemanticRetrievalService(repository, embedding_service)

    results = await service.retrieve("architecture leadership", limit=3)

    embedding_service.embed.assert_awaited_once()
    request = embedding_service.embed.await_args.args[0]
    assert request.inputs == ["architecture leadership"]

    repository.search_similar.assert_called_once_with(
        query_embedding=[1.0, 0.0],
        embedding_model="test-model",
        limit=3,
        document_id=None,
        user_id=None,
    )

    assert results == [
        KnowledgeSearchResult(
            chunk_id="chunk-1",
            document_id="document-1",
            content="Drive architecture decisions.",
            heading_path=["Technical Leadership", "Architecture"],
            document_type="role",
            scope_type="employee",
            scope_id="user-1",
            metadata={"source_page": 3},
            similarity=0.97,
        )
    ]


@pytest.mark.asyncio
async def test_semantic_retrieval_rejects_empty_query():
    service = SemanticRetrievalService(MagicMock(), MagicMock())

    with pytest.raises(ValueError, match="Query must not be empty"):
        await service.retrieve("   ")


@pytest.mark.asyncio
async def test_semantic_retrieval_requires_model_from_provider():
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(
        return_value=EmbeddingResponse(
            embeddings=[[1.0, 0.0]],
            model=None,
        )
    )

    service = SemanticRetrievalService(MagicMock(), embedding_service)

    with pytest.raises(ValueError, match="embedding model"):
        await service.retrieve("architecture")

@pytest.mark.asyncio
async def test_semantic_retrieval_requires_exactly_one_query_embedding():
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(
        return_value=EmbeddingResponse(
            embeddings=[],
            model="test-model",
        )
    )

    service = SemanticRetrievalService(MagicMock(), embedding_service)

    with pytest.raises(
        ValueError,
        match="Embedding provider must return one query vector",
    ):
        await service.retrieve("architecture")


@pytest.mark.asyncio
async def test_semantic_retrieval_rejects_multiple_query_embeddings():
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(
        return_value=EmbeddingResponse(
            embeddings=[
                [1.0, 0.0],
                [0.0, 1.0],
            ],
            model="test-model",
        )
    )

    service = SemanticRetrievalService(MagicMock(), embedding_service)

    with pytest.raises(
        ValueError,
        match="Embedding provider must return one query vector",
    ):
        await service.retrieve("architecture")


@pytest.mark.asyncio
async def test_semantic_retrieval_returns_empty_list_when_no_matches():
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(
        return_value=EmbeddingResponse(
            embeddings=[[1.0, 0.0]],
            model="test-model",
        )
    )

    repository = MagicMock()
    repository.search_similar.return_value = []

    service = SemanticRetrievalService(repository, embedding_service)

    results = await service.retrieve("architecture")

    assert results == []
    repository.search_similar.assert_called_once_with(
        query_embedding=[1.0, 0.0],
        embedding_model="test-model",
        limit=5,
        document_id=None,
        user_id=None,
    )