from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.document_chunk import DocumentChunkDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentScopeType, DocumentType
from app.models.user import UserCreate
from app.repositories.document import DocumentRepository
from app.repositories.document_chunk import DocumentChunkRepository
from app.services.user import UserService


@pytest.mark.integration
def test_document_chunk_repository_create_and_read():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())
    chunk_ids = [str(uuid4()), str(uuid4())]

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Chunk User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        DocumentRepository(session).create(
            document_id=document_id,
            user_id=user_id,
            document_type=DocumentType.ROLE,
            file_name="role_expectations.pdf",
            content_type="application/pdf",
            storage_path=f"documents/{user_id}/role_expectations.pdf",
        )

        repository = DocumentChunkRepository(session)

        repository.create(
            chunk_id=chunk_ids[1],
            document_id=document_id,
            chunk_index=1,
            content="Drive architecture decisions.",
            heading_path=[
                "Engineering Expectations",
                "Technical Leadership",
                "Architecture",
            ],
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.EMPLOYEE,
            scope_id=user_id,
            metadata={"source_page": 3},
        )
        repository.create(
            chunk_id=chunk_ids[0],
            document_id=document_id,
            chunk_index=0,
            content="Lead technical direction.",
            heading_path=["Engineering Expectations", "Technical Leadership"],
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.EMPLOYEE,
            scope_id=user_id,
            metadata={},
        )
        session.commit()
        session.expire_all()

        result = repository.get_by_id(chunk_ids[1])

        assert result is not None
        assert result.id == chunk_ids[1]
        assert result.document_id == document_id
        assert result.chunk_index == 1
        assert result.content == "Drive architecture decisions."
        assert result.heading_path == [
            "Engineering Expectations",
            "Technical Leadership",
            "Architecture",
        ]
        assert result.document_type == DocumentType.ROLE
        assert result.scope_type == DocumentScopeType.EMPLOYEE
        assert result.scope_id == user_id
        assert result.metadata_ == {"source_page": 3}
        assert result.created_at is not None
        assert result.updated_at is not None

        by_document = repository.get_by_document_id(document_id)

        assert [chunk.id for chunk in by_document] == [
            chunk_ids[0],
            chunk_ids[1],
        ]

    finally:
        session.execute(
            delete(DocumentChunkDB).where(
                DocumentChunkDB.document_id == document_id
            )
        )
        session.execute(delete(DocumentDB).where(DocumentDB.id == document_id))

        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))

        session.commit()
        session.close()


@pytest.mark.integration
def test_document_chunk_repository_delete_by_document_id():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())
    chunk_ids = [str(uuid4()), str(uuid4())]

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Chunk Delete User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        DocumentRepository(session).create(
            document_id=document_id,
            user_id=user_id,
            document_type=DocumentType.ROLE,
            file_name="role_expectations.pdf",
            content_type="application/pdf",
            storage_path=f"documents/{user_id}/role_expectations.pdf",
        )

        repository = DocumentChunkRepository(session)

        for index, chunk_id in enumerate(chunk_ids):
            repository.create(
                chunk_id=chunk_id,
                document_id=document_id,
                chunk_index=index,
                content=f"Chunk {index}",
                heading_path=[],
                document_type=DocumentType.ROLE,
                scope_type=DocumentScopeType.EMPLOYEE,
                scope_id=user_id,
                metadata={},
            )

        session.commit()

        deleted_count = repository.delete_by_document_id(document_id)
        session.commit()

        assert deleted_count == 2
        assert repository.get_by_document_id(document_id) == []

    finally:
        session.execute(
            delete(DocumentChunkDB).where(
                DocumentChunkDB.document_id == document_id
            )
        )
        session.execute(delete(DocumentDB).where(DocumentDB.id == document_id))

        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))

        session.commit()
        session.close()