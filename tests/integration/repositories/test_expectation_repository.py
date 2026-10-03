from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.expectation import DocumentExpectationDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentType
from app.models.expectation import ExpectationCategory
from app.models.user import UserCreate
from app.repositories.document import DocumentRepository
from app.repositories.expectation import DocumentExpectationRepository
from app.services.user import UserService


@pytest.mark.integration
def test_document_expectation_repository_create_and_read():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())
    expectation_id = str(uuid4())

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Expectation User",
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

        repository = DocumentExpectationRepository(session)

        repository.create(
            expectation_id=expectation_id,
            document_id=document_id,
            category=ExpectationCategory.ARCHITECTURE,
            description="Lead architecture initiatives",
            evidence_hints=[
                "Architecture decisions",
                "Design documents",
            ],
            source_page=2,
            source_section="Technical Leadership",
            source_text_span="Lead architecture initiatives",
            confidence=0.94,
        )
        session.commit()
        session.expire_all()

        result = repository.get_by_id(expectation_id)

        assert result is not None
        assert result.id == expectation_id
        assert result.document_id == document_id
        assert result.category == ExpectationCategory.ARCHITECTURE
        assert result.description == "Lead architecture initiatives"
        assert result.evidence_hints == [
            "Architecture decisions",
            "Design documents",
        ]
        assert result.source_page == 2
        assert result.source_section == "Technical Leadership"
        assert result.source_text_span == "Lead architecture initiatives"
        assert result.confidence == 0.94
        assert result.created_at is not None
        assert result.updated_at is not None

        by_document = repository.get_by_document_id(document_id)
        assert len(by_document) == 1
        assert by_document[0].id == expectation_id

        by_category = repository.get_by_document_and_category(
            document_id,
            ExpectationCategory.ARCHITECTURE,
        )
        assert len(by_category) == 1
        assert by_category[0].id == expectation_id

    finally:
        session.execute(
            delete(DocumentExpectationDB).where(
                DocumentExpectationDB.id == expectation_id
            )
        )
        session.execute(
            delete(DocumentDB).where(DocumentDB.id == document_id)
        )

        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))

        session.commit()
        session.close()


@pytest.mark.integration
def test_document_expectation_repository_delete_by_document_id():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())
    expectation_ids = [str(uuid4()), str(uuid4())]

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Expectation Delete User",
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

        repository = DocumentExpectationRepository(session)

        for expectation_id, category in zip(
            expectation_ids,
            [
                ExpectationCategory.ARCHITECTURE,
                ExpectationCategory.MENTORING,
            ],
            strict=True,
        ):
            repository.create(
                expectation_id=expectation_id,
                document_id=document_id,
                category=category,
                description=f"Expectation {expectation_id}",
                evidence_hints=[],
                confidence=0.9,
            )

        session.commit()

        deleted_count = repository.delete_by_document_id(document_id)
        session.commit()

        assert deleted_count == 2
        assert repository.get_by_document_id(document_id) == []

    finally:
        session.execute(
            delete(DocumentExpectationDB).where(
                DocumentExpectationDB.document_id == document_id
            )
        )
        session.execute(
            delete(DocumentDB).where(DocumentDB.id == document_id)
        )

        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))

        session.commit()
        session.close()
