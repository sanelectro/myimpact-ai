from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentScopeType, DocumentType
from app.models.user import UserCreate
from app.repositories.document import DocumentRepository
from app.services.user import UserService


@pytest.mark.integration
def test_document_scope_is_persisted_and_queryable():
    session = SessionLocal()
    user_id = None
    document_id = str(uuid4())

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Scope User",
                email=f"{uuid4()}@example.com",
                role="Lead Engineer",
            )
        )
        user_id = user.id

        repository = DocumentRepository(session)

        document = repository.create(
            document_id=document_id,
            user_id=user_id,
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.ROLE,
            scope_id="lead_engineer",
            file_name="lead-engineer-role.pdf",
            content_type="application/pdf",
            storage_path=(
                f"documents/roles/lead_engineer/{document_id}.pdf"
            ),
        )
        session.commit()

        stored = repository.get_by_id(document_id)
        assert stored is not None
        assert stored.scope_type == DocumentScopeType.ROLE
        assert stored.scope_id == "lead_engineer"

        role_documents = repository.get_by_scope(
            DocumentScopeType.ROLE,
            "lead_engineer",
        )

        assert any(
            item.id == document_id
            for item in role_documents
        )

    finally:
        session.execute(
            delete(DocumentDB).where(
                DocumentDB.id == document_id
            )
        )

        if user_id:
            session.execute(
                delete(UserDB).where(
                    UserDB.id == user_id
                )
            )

        session.commit()
        session.close()
