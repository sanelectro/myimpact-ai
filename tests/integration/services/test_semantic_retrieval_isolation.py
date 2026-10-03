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
from app.services.knowledge.document_embedding import (
    DocumentChunkEmbeddingService,
)
from app.services.knowledge.semantic_retrieval import SemanticRetrievalService
from app.services.user import UserService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_retrieval_isolated_by_user():
    session = SessionLocal()

    user_a_id = None
    user_b_id = None
    document_a_id = str(uuid4())
    document_b_id = str(uuid4())
    chunk_a_id = str(uuid4())
    chunk_b_id = str(uuid4())

    try:
        # ---------------------------------------------------------
        # 1. Create two users
        # ---------------------------------------------------------
        user_service = UserService(session)

        user_a = user_service.create_user(
            UserCreate(
                name="M3 Isolation User A",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_a_id = user_a.id

        user_b = user_service.create_user(
            UserCreate(
                name="M3 Isolation User B",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_b_id = user_b.id

        # ---------------------------------------------------------
        # 2. Create one document/chunk for each user
        # ---------------------------------------------------------
        document_repository = DocumentRepository(session)
        chunk_repository = DocumentChunkRepository(session)

        document_repository.create(
            document_id=document_a_id,
            user_id=user_a_id,
            document_type=DocumentType.DEVELOPMENT,
            file_name="user-a.md",
            content_type="text/markdown",
            storage_path=f"documents/{user_a_id}/user-a.md",
        )

        document_repository.create(
            document_id=document_b_id,
            user_id=user_b_id,
            document_type=DocumentType.DEVELOPMENT,
            file_name="user-b.md",
            content_type="text/markdown",
            storage_path=f"documents/{user_b_id}/user-b.md",
        )

        chunk_repository.create(
            chunk_id=chunk_a_id,
            document_id=document_a_id,
            chunk_index=0,
            content="I drove architecture decisions for the voyage platform.",
            heading_path=["Technical Leadership", "Architecture"],
            document_type=DocumentType.DEVELOPMENT,
            scope_type=DocumentScopeType.EMPLOYEE,
            scope_id=user_a_id,
            metadata={},
        )

        chunk_repository.create(
            chunk_id=chunk_b_id,
            document_id=document_b_id,
            chunk_index=0,
            content="I led the migration of the analytics platform.",
            heading_path=["Technical Leadership", "Migration"],
            document_type=DocumentType.DEVELOPMENT,
            scope_type=DocumentScopeType.EMPLOYEE,
            scope_id=user_b_id,
            metadata={},
        )

        # ---------------------------------------------------------
        # 3. Generate embeddings for both documents
        # ---------------------------------------------------------
        embedding_service = MockEmbeddingService(dimensions=8)
        embedding_repository = DocumentChunkEmbeddingRepository(session)
        embedding_indexer = DocumentChunkEmbeddingService(
            session,
            embedding_service,
        )

        assert await embedding_indexer.embed_document(document_a_id) == 1
        assert await embedding_indexer.embed_document(document_b_id) == 1

        # ---------------------------------------------------------
        # 4. Retrieve as User A
        #
        # Query is deliberately the exact content of User B's chunk.
        # Without user filtering this would strongly match User B's
        # chunk. The retrieval layer must still return no result.
        # ---------------------------------------------------------
        retrieval = SemanticRetrievalService(
            embedding_repository,
            embedding_service,
        )

        results = await retrieval.retrieve(
            "I led the migration of the analytics platform.",
            user_id=user_a_id,
            limit=10,
        )

        # ---------------------------------------------------------
        # 5. User A must never receive User B's chunk
        # ---------------------------------------------------------
        result_chunk_ids = {result.chunk_id for result in results}

        assert chunk_b_id not in result_chunk_ids

        # User A's own chunk may or may not be semantically similar
        # to the query, so the important security assertion is that
        # User B's chunk is never returned.
        for result in results:
            assert result.scope_id == user_a_id
            assert result.chunk_id != chunk_b_id

    finally:
        # ---------------------------------------------------------
        # 6. Cleanup
        # ---------------------------------------------------------
        session.execute(
            delete(DocumentChunkEmbeddingDB).where(
                DocumentChunkEmbeddingDB.chunk_id.in_(
                    [chunk_a_id, chunk_b_id]
                )
            )
        )

        session.execute(
            delete(DocumentChunkDB).where(
                DocumentChunkDB.id.in_(
                    [chunk_a_id, chunk_b_id]
                )
            )
        )

        session.execute(
            delete(DocumentDB).where(
                DocumentDB.id.in_(
                    [document_a_id, document_b_id]
                )
            )
        )

        if user_a_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_a_id)
            )

        if user_b_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_b_id)
            )

        session.commit()
        session.close()