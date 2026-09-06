from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.document import get_document_service
from app.db.models.document import DocumentDB
from app.main import app
from app.models.document import DocumentType
from app.services.document import DocumentService

client = TestClient(app)


def _document():
    document = MagicMock(spec=DocumentDB)
    document.id = "document-1"
    document.user_id = "user-1"
    document.document_type = DocumentType.GOAL
    document.file_name = "goals.pdf"
    document.content_type = "application/pdf"
    document.storage_path = "/tmp/storage/goals.pdf"
    document.extracted_text = None
    document.source = "employee_upload"
    document.effective_start = None
    document.effective_end = None
    document.content_hash = "a" * 64
    document.status = "uploaded"
    document.created_at = "2026-09-06T10:00:00Z"
    document.updated_at = "2026-09-06T10:00:00Z"
    return document


def test_upload_document():
    service = MagicMock(spec=DocumentService)
    service.upload_document.return_value = _document()

    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents",
            data={
                "user_id": "user-1",
                "document_type": "goal",
            },
            files={
                "file": (
                    "goals.pdf",
                    b"pdf-content",
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 201
        assert response.json()["id"] == "document-1"
        assert response.json()["document_type"] == "goal"

        service.upload_document.assert_called_once()
        kwargs = service.upload_document.call_args.kwargs
        assert kwargs["user_id"] == "user-1"
        assert kwargs["document_type"] == DocumentType.GOAL
        assert kwargs["file_name"] == "goals.pdf"
        assert kwargs["content_type"] == "application/pdf"
        assert kwargs["content"] == b"pdf-content"
    finally:
        app.dependency_overrides.clear()


def test_upload_document_rejects_unsupported_extension():
    service = MagicMock(spec=DocumentService)
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents",
            data={
                "user_id": "user-1",
                "document_type": "goal",
            },
            files={
                "file": (
                    "notes.txt",
                    b"text",
                    "text/plain",
                )
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "Only PDF and DOCX files are supported."
        )
        service.upload_document.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_upload_document_rejects_empty_file():
    service = MagicMock(spec=DocumentService)
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents",
            data={
                "user_id": "user-1",
                "document_type": "goal",
            },
            files={
                "file": (
                    "empty.pdf",
                    b"",
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == (
            "The uploaded file is empty."
        )
        service.upload_document.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_get_document_by_id():
    service = MagicMock(spec=DocumentService)
    service.get_document_by_id.return_value = _document()
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get("/documents/document-1")
        assert response.status_code == 200
        assert response.json()["id"] == "document-1"
        service.get_document_by_id.assert_called_once_with("document-1")
    finally:
        app.dependency_overrides.clear()


def test_get_document_by_id_returns_404():
    service = MagicMock(spec=DocumentService)
    service.get_document_by_id.return_value = None
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get("/documents/missing")
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found"
    finally:
        app.dependency_overrides.clear()


def test_get_documents_by_user_id():
    service = MagicMock(spec=DocumentService)
    service.get_documents_by_user_id.return_value = [_document()]
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get("/documents/user/user-1")
        assert response.status_code == 200
        assert len(response.json()) == 1
        service.get_documents_by_user_id.assert_called_once_with("user-1")
    finally:
        app.dependency_overrides.clear()


def test_get_documents_by_user_and_type():
    service = MagicMock(spec=DocumentService)
    service.get_documents_by_user_and_type.return_value = [_document()]
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get(
            "/documents/user/user-1/type/goal",
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        service.get_documents_by_user_and_type.assert_called_once_with(
            "user-1",
            DocumentType.GOAL,
        )
    finally:
        app.dependency_overrides.clear()
