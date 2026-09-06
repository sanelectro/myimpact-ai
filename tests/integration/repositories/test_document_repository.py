from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentType
from app.models.user import UserCreate
from app.repositories.document import DocumentRepository
from app.services.user import UserService


@pytest.mark.integration
def test_document_repository_create_and_read():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Document User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        repository = DocumentRepository(session)

        repository.create(
            document_id=document_id,
            user_id=user_id,
            document_type=DocumentType.GOAL,
            file_name="annual_goals.pdf",
            content_type="application/pdf",
            storage_path=f"documents/{user_id}/annual_goals.pdf",
            source="employee_upload",
            effective_start=date(2026, 1, 1),
            effective_end=date(2026, 12, 31),
            content_hash="m3-document-hash",
        )
        session.commit()

        result = repository.get_by_id(document_id)

        assert result is not None
        assert result.id == document_id
        assert result.user_id == user_id
        assert result.document_type == DocumentType.GOAL
        assert result.file_name == "annual_goals.pdf"
        assert result.content_type == "application/pdf"
        assert result.storage_path.endswith("annual_goals.pdf")
        assert result.effective_start == date(2026, 1, 1)
        assert result.effective_end == date(2026, 12, 31)

        by_user = repository.get_by_user_id(user_id)

        assert len(by_user) == 1
        assert by_user[0].id == document_id

        by_type = repository.get_by_user_and_type(
            user_id,
            DocumentType.GOAL,
        )

        assert len(by_type) == 1
        assert by_type[0].id == document_id

    finally:
        session.execute(
            delete(DocumentDB).where(DocumentDB.id == document_id)
        )

        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )

        session.commit()
        session.close()
