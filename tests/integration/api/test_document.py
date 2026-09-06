from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.routes.document import get_document_storage
from app.db.models.document import DocumentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserCreate
from app.services.user import UserService
from app.storage.local import LocalFileStorage

client = TestClient(app)


@pytest.mark.integration
def test_upload_document_api_persists_file_and_record(tmp_path: Path):
    session = SessionLocal()
    user_id = None
    document_id = None
    storage = LocalFileStorage(tmp_path)

    app.dependency_overrides[get_document_storage] = lambda: storage

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Document API User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        response = client.post(
            "/documents",
            data={
                "user_id": user_id,
                "document_type": "goal",
            },
            files={
                "file": (
                    "annual_goals.pdf",
                    b"synthetic annual goal document",
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 201

        data = response.json()
        document_id = data["id"]

        assert data["user_id"] == user_id
        assert data["document_type"] == "goal"
        assert data["file_name"] == "annual_goals.pdf"
        assert data["content_type"] == "application/pdf"
        assert data["status"] == "uploaded"

        stored = session.get(DocumentDB, document_id)

        assert stored is not None
        assert stored.user_id == user_id
        assert stored.storage_path

        assert storage.exists(stored.storage_path)
        assert storage.read(stored.storage_path) == (
            b"synthetic annual goal document"
        )

        get_response = client.get(
            f"/documents/{document_id}",
        )

        assert get_response.status_code == 200
        assert get_response.json()["id"] == document_id

    finally:
        app.dependency_overrides.clear()

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
