from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.document_chunk_embedding import DocumentChunkEmbedding


def test_document_chunk_embedding_model():
    now = datetime.now(UTC)
    embedding = DocumentChunkEmbedding(
        id="embedding-1",
        chunk_id="chunk-1",
        embedding=[0.1, 0.2, 0.3],
        embedding_model="mock-embedding",
        embedding_dimensions=3,
        created_at=now,
        updated_at=now,
    )

    assert embedding.chunk_id == "chunk-1"
    assert embedding.embedding == [0.1, 0.2, 0.3]
    assert embedding.embedding_dimensions == 3


def test_document_chunk_embedding_rejects_empty_vector():
    with pytest.raises(ValidationError):
        DocumentChunkEmbedding(
            id="embedding-1",
            chunk_id="chunk-1",
            embedding=[],
            embedding_model="mock-embedding",
            embedding_dimensions=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
