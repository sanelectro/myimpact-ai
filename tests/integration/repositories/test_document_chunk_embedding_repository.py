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
from app.services.user import UserService


@pytest.mark.integration
def test_embedding_repository_upsert_and_semantic_retrieval():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())
    chunk_ids = [str(uuid4()), str(uuid4())]

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Embedding User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        DocumentRepository(session).create(
            document_id=document_id,
            user_id=user_id,
            document_type=DocumentType.ROLE,
            file_name="role.pdf",
            content_type="application/pdf",
            storage_path=f"documents/{user_id}/role.pdf",
        )

        chunk_repository = DocumentChunkRepository(session)
        chunk_repository.create(
            chunk_id=chunk_ids[0],
            document_id=document_id,
            chunk_index=0,
            content="Drive architecture decisions.",
            heading_path=["Technical Leadership", "Architecture"],
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.EMPLOYEE,
            scope_id=user_id,
            metadata={},
        )
        chunk_repository.create(
            chunk_id=chunk_ids[1],
            document_id=document_id,
            chunk_index=1,
            content="Write clear technical documentation.",
            heading_path=["Technical Leadership", "Documentation"],
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.EMPLOYEE,
            scope_id=user_id,
            metadata={},
        )

        repository = DocumentChunkEmbeddingRepository(session)
        repository.upsert(
            chunk_id=chunk_ids[0],
            embedding=[1.0, 0.0, 0.0],
            embedding_model="test-model",
        )
        repository.upsert(
            chunk_id=chunk_ids[1],
            embedding=[0.0, 1.0, 0.0],
            embedding_model="test-model",
        )
        session.commit()

        stored = repository.get_by_chunk_id(chunk_ids[0])
        assert stored is not None
        assert stored.embedding == [1.0, 0.0, 0.0]
        assert stored.embedding_model == "test-model"
        assert stored.embedding_dimensions == 3

        results = repository.search_similar(
            query_embedding=[1.0, 0.0, 0.0],
            embedding_model="test-model",
            limit=2,
        )

        assert [chunk.id for chunk, _ in results] == chunk_ids
        assert results[0][1] == pytest.approx(1.0)
        assert results[1][1] == pytest.approx(0.0)

        repository.upsert(
            chunk_id=chunk_ids[0],
            embedding=[0.0, 0.0, 1.0],
            embedding_model="test-model-v2",
        )
        session.commit()

        updated = repository.get_by_chunk_id(chunk_ids[0])
        assert updated is not None
        assert updated.embedding_model == "test-model-v2"
        assert updated.embedding_dimensions == 3

    finally:
        session.execute(
            delete(DocumentChunkEmbeddingDB).where(
                DocumentChunkEmbeddingDB.chunk_id.in_(chunk_ids)
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
