from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.expectations import get_document_service, get_expectation_service
from app.db.models.document import DocumentDB
from app.db.models.expectation import DocumentExpectationDB
from app.main import app
from app.models.document import DocumentScopeType, DocumentStatus, DocumentType
from app.models.expectation import ExpectationCategory
from app.services.document import DocumentService
from app.services.document_expectation_api import DocumentExpectationApiService

client = TestClient(app)


def _document(user_id="user-1"):
    now = datetime.now(UTC)
    return DocumentDB(
        id="doc-1", user_id=user_id, file_name="role.pdf", content_type="application/pdf",
        document_type=DocumentType.ROLE, scope_type=DocumentScopeType.EMPLOYEE,
        status=DocumentStatus.PROCESSED, created_at=now, updated_at=now,
    )


def _expectation():
    now = datetime.now(UTC)
    return DocumentExpectationDB(
        id="exp-1", document_id="doc-1", category=ExpectationCategory.ARCHITECTURE,
        description="Lead architecture decisions", evidence_hints=["architecture"],
        confidence=0.9, created_at=now, updated_at=now,
    )


def test_document_expectations_enforce_document_ownership():
    document_service = MagicMock(spec=DocumentService)
    expectation_service = MagicMock(spec=DocumentExpectationApiService)
    document_service.get_document_by_id.return_value = _document(user_id="owner")
    app.dependency_overrides[get_document_service] = lambda: document_service
    app.dependency_overrides[get_expectation_service] = lambda: expectation_service
    try:
        response = client.get(
            "/api/v1/knowledge/documents/doc-1/expectations",
            params={"user_id": "other-user"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    expectation_service.get_by_document_id.assert_not_called()


def test_document_expectations_returns_product_contract():
    document_service = MagicMock(spec=DocumentService)
    expectation_service = MagicMock(spec=DocumentExpectationApiService)
    document_service.get_document_by_id.return_value = _document()
    expectation_service.get_by_document_id.return_value = [_expectation()]
    app.dependency_overrides[get_document_service] = lambda: document_service
    app.dependency_overrides[get_expectation_service] = lambda: expectation_service
    try:
        response = client.get(
            "/api/v1/knowledge/documents/doc-1/expectations",
            params={"user_id": "user-1"},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()[0]["id"] == "exp-1"
