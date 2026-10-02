from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.routes.document import (
    get_document_classification_service,
    get_document_expectation_extraction_service,
    get_document_storage,
)
from app.db.models.document import DocumentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.document import DocumentClassification, DocumentType
from app.models.expectation import ExpectationExtractionResult
from app.models.user import UserCreate
from app.services.document_expectation import DocumentExpectationExtractionService
from app.services.user import UserService
from app.storage.local import LocalFileStorage

client = TestClient(app)


@pytest.mark.integration
def test_upload_document_api_persists_processed_document(tmp_path: Path):
    session = SessionLocal()
    user_id = None
    document_id = None
    storage = LocalFileStorage(tmp_path)
    classification_service = AsyncMock()
    classification_service.classify.return_value = DocumentClassification(
        document_type=DocumentType.GOAL,
        confidence=0.94,
        reason="Contains annual objectives.",
    )

    expectation_extraction_service = AsyncMock(
        spec=DocumentExpectationExtractionService
    )
    expectation_extraction_service.extract.return_value = (
        ExpectationExtractionResult(expectations=[])
    )

    app.dependency_overrides[get_document_storage] = lambda: storage
    app.dependency_overrides[get_document_classification_service] = (
        lambda: classification_service
    )

    app.dependency_overrides[get_document_expectation_extraction_service] = (
        lambda: expectation_extraction_service
    )

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Document API User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        source_file = (
            Path(__file__).resolve().parents[3]
            / "demo-data"
            / "MyImpact_Demo_Lead_Engineer_Expectations.pdf"
        )

        response = client.post(
            "/documents",
            data={
                "user_id": user_id,
                "document_type": "goal",
            },
            files={
                "file": (
                    source_file.name,
                    source_file.read_bytes(),
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 201

        data = response.json()
        document_id = data["id"]

        assert data["user_id"] == user_id
        assert data["document_type"] == "goal"
        assert data["status"] == "processed"
        assert data["scope_type"] == "employee"
        assert data["scope_id"] == user_id
        assert data["classification_type"] == "goal"
        assert data["classification_confidence"] == 0.94
        assert data["classification_reason"] == "Contains annual objectives."
        assert data["extracted_content_path"]

        stored = session.get(DocumentDB, document_id)

        assert stored is not None
        assert stored.user_id == user_id
        assert stored.storage_path
        assert stored.extracted_content_path
        assert stored.classification_type == DocumentType.GOAL
        assert stored.classification_confidence == 0.94

        assert storage.exists(stored.storage_path)
        assert storage.exists(stored.extracted_content_path)
        assert storage.read(stored.extracted_content_path)

        classification_service.classify.assert_awaited_once()

        expectation_extraction_service.extract.assert_awaited_once()

        get_response = client.get(
            f"/documents/{document_id}",
        )

        assert get_response.status_code == 200
        assert get_response.json()["id"] == document_id
        assert get_response.json()["classification_type"] == "goal"

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
