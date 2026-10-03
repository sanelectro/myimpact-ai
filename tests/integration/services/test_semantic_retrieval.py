from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.document_chunk import DocumentChunkDB
from app.db.models.document_chunk_embedding import DocumentChunkEmbeddingDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentScopeType, DocumentType
from app.models.user import UserCreate
from app.repositories.document import DocumentRepository
from app.repositories.document_chunk import DocumentChunkRepository
from app.repositories.document_chunk_embedding import (
    DocumentChunkEmbeddingRepository,
)
from app.services.embedding.mock_service import MockEmbeddingService
from app.services.knowledge.document_embedding import DocumentChunkEmbeddingService
from app.services.knowledge.semantic_retrieval import SemanticRetrievalService
from app.services.user import UserService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_retrieval_end_to_end_with_mock_embeddings():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())
    chunk_id = str(uuid4())

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Semantic User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        DocumentRepository(session).create(
            document_id=document_id,
            user_id=user_id,
            document_type=DocumentType.DEVELOPMENT,
            file_name="development.md",
            content_type="text/markdown",
            storage_path=f"documents/{user_id}/development.md",
        )

        DocumentChunkRepository(session).create(
            chunk_id=chunk_id,
            document_id=document_id,
            chunk_index=0,
            content="I drove architecture decisions for the voyage platform.",
            heading_path=["Technical Leadership", "Architecture"],
            document_type=DocumentType.DEVELOPMENT,
            scope_type=DocumentScopeType.EMPLOYEE,
            scope_id=user_id,
            metadata={},
        )

        embedding_service = MockEmbeddingService(dimensions=8)
        embedding_repository = DocumentChunkEmbeddingRepository(session)
        embedding_indexer = DocumentChunkEmbeddingService(
            session,
            embedding_service,
        )

        count = await embedding_indexer.embed_document(document_id)
        assert count == 1

        retrieval = SemanticRetrievalService(
            embedding_repository,
            embedding_service,
        )
        results = await retrieval.retrieve(
            "I drove architecture decisions for the voyage platform.",
            user_id=user_id,
            limit=1,
        )

        assert len(results) == 1
        assert results[0].chunk_id == chunk_id
        assert results[0].content.startswith("I drove architecture decisions")
        assert results[0].similarity == pytest.approx(1.0)

    finally:
        session.execute(
            delete(DocumentChunkEmbeddingDB).where(
                DocumentChunkEmbeddingDB.chunk_id == chunk_id
            )
        )
        session.execute(
            delete(DocumentChunkDB).where(DocumentChunkDB.document_id == document_id)
        )
        session.execute(delete(DocumentDB).where(DocumentDB.id == document_id))
        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()
