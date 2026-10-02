from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.document import get_document_service
from app.db.models.document import DocumentDB
from app.db.models.expectation import DocumentExpectationDB
from app.main import app
from app.models.expectation import ExpectationCategory
from app.services.document import DocumentService

client = TestClient(app)


def _document():
    document = MagicMock(spec=DocumentDB)
    document.id = "document-1"
    return document


def _expectation():
    expectation = MagicMock(spec=DocumentExpectationDB)
    expectation.id = "expectation-1"
    expectation.document_id = "document-1"
    expectation.category = ExpectationCategory.TECHNICAL_LEADERSHIP
    expectation.description = "Improve reliability ownership."
    expectation.evidence_hints = ["Reliability initiatives"]
    expectation.source_page = 1
    expectation.source_section = "2026 Goals"
    expectation.source_text_span = "Improve reliability ownership."
    expectation.confidence = 0.91
    expectation.created_at = datetime(2026, 10, 2, tzinfo=UTC)
    expectation.updated_at = datetime(2026, 10, 2, tzinfo=UTC)
    return expectation


def test_get_document_expectations():
    service = MagicMock(spec=DocumentService)
    service.get_document_by_id.return_value = _document()
    service.get_document_expectations.return_value = [_expectation()]
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get("/documents/document-1/expectations")

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": "expectation-1",
                "document_id": "document-1",
                "category": "technical_leadership",
                "description": "Improve reliability ownership.",
                "evidence_hints": ["Reliability initiatives"],
                "source_page": 1,
                "source_section": "2026 Goals",
                "source_text_span": "Improve reliability ownership.",
                "confidence": 0.91,
                "created_at": "2026-10-02T00:00:00Z",
                "updated_at": "2026-10-02T00:00:00Z",
            }
        ]
        service.get_document_by_id.assert_called_once_with("document-1")
        service.get_document_expectations.assert_called_once_with(
            "document-1"
        )
    finally:
        app.dependency_overrides.clear()


def test_get_document_expectations_returns_empty_list():
    service = MagicMock(spec=DocumentService)
    service.get_document_by_id.return_value = _document()
    service.get_document_expectations.return_value = []
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get("/documents/document-1/expectations")

        assert response.status_code == 200
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_get_document_expectations_returns_404_for_missing_document():
    service = MagicMock(spec=DocumentService)
    service.get_document_by_id.return_value = None
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get("/documents/missing/expectations")

        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found"
        service.get_document_expectations.assert_not_called()
    finally:
        app.dependency_overrides.clear()