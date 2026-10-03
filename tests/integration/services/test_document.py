from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentType
from app.models.user import UserCreate
from app.services.document import DocumentService
from app.services.user import UserService
from app.storage.local import LocalFileStorage


@pytest.mark.integration
def test_document_service_upload_persists_file_and_metadata(tmp_path: Path):
    session = SessionLocal()
    user_id = None
    document_id = None
    storage = LocalFileStorage(tmp_path)

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Upload User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        service = DocumentService(
            session,
            storage=storage,
        )

        document = service.upload_document(
            user_id=user_id,
            document_type=DocumentType.ONE_TO_ONE,
            file_name="one-to-one.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            content=b"Manager feedback and development discussion.",
        )

        document_id = document.id

        assert document.user_id == user_id
        assert document.document_type == DocumentType.ONE_TO_ONE
        assert document.file_name == "one-to-one.docx"
        assert document.status.value == "uploaded"
        assert len(document.content_hash) == 64

        assert storage.exists(document.storage_path)
        assert storage.read(document.storage_path) == (
            b"Manager feedback and development discussion."
        )

        stored_document = session.get(DocumentDB, document_id)

        assert stored_document is not None
        assert stored_document.storage_path == document.storage_path

    finally:
        if document_id:
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
