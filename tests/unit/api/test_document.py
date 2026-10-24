import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.document import (
    MAX_DOCUMENT_SIZE_BYTES,
    _validate_upload,
    get_document_service,
)
from app.db.models.document import DocumentDB
from app.exceptions import (
    DocumentClassificationError,
    DocumentExtractionError,
)
from app.main import app
from app.models.document import (
    DocumentScopeType,
    DocumentStatus,
    DocumentType,
)
from app.services.document import DocumentService

client = TestClient(app)


def _document(
    *,
    status: DocumentStatus = DocumentStatus.UPLOADED,
    extracted_content_path: str | None = None,
):
    document = MagicMock(spec=DocumentDB)
    document.id = "document-1"
    document.user_id = "user-1"
    document.document_type = DocumentType.GOAL
    document.scope_type = DocumentScopeType.EMPLOYEE
    document.scope_id = "user-1"
    document.file_name = "goals.pdf"
    document.content_type = "application/pdf"
    document.storage_path = "storage/goals.pdf"
    document.extracted_content_path = extracted_content_path
    document.classification_type = None
    document.classification_confidence = None
    document.classification_reason = None
    document.classification_error = None
    document.classified_at = None
    document.source = "employee_upload"
    document.effective_start = None
    document.effective_end = None
    document.content_hash = "a" * 64
    document.status = status
    document.created_at = "2026-09-06T10:00:00Z"
    document.updated_at = "2026-09-06T10:00:00Z"
    return document


def test_upload_document():
    service = MagicMock(spec=DocumentService)
    uploaded = _document()
    uploaded.status = DocumentStatus.PROCESSED
    uploaded.extracted_content_path = "storage/document-1/extracted.md"
    service.upload_document.return_value = uploaded
    service.process_document.return_value = uploaded

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
        assert response.json()["scope_type"] == "employee"
        assert response.json()["scope_id"] == "user-1"

        service.upload_document.assert_called_once()
        service.process_document.assert_awaited_once_with("document-1")
        kwargs = service.upload_document.call_args.kwargs
        assert kwargs["user_id"] == "user-1"
        assert kwargs["document_type"] == DocumentType.GOAL
        assert kwargs["scope_type"] == DocumentScopeType.EMPLOYEE
        assert kwargs["scope_id"] is None
        assert kwargs["file_name"] == "goals.pdf"
        assert kwargs["content_type"] == "application/pdf"
        assert kwargs["content"] == b"pdf-content"
    finally:
        app.dependency_overrides.clear()


def test_upload_role_document_passes_scope():
    service = MagicMock(spec=DocumentService)
    document = _document()
    document.document_type = DocumentType.ROLE
    document.scope_type = DocumentScopeType.ROLE
    document.scope_id = "lead_engineer"
    service.upload_document.return_value = document
    service.process_document.return_value = document

    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents",
            data={
                "user_id": "admin-1",
                "document_type": "role",
                "scope_type": "role",
                "scope_id": "lead_engineer",
            },
            files={
                "file": (
                    "lead-engineer-role.pdf",
                    b"role-content",
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 201
        assert response.json()["scope_type"] == "role"
        assert response.json()["scope_id"] == "lead_engineer"

        service.process_document.assert_awaited_once_with("document-1")
        kwargs = service.upload_document.call_args.kwargs
        assert kwargs["scope_type"] == DocumentScopeType.ROLE
        assert kwargs["scope_id"] == "lead_engineer"
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


@pytest.mark.parametrize(
    ("file_name", "content_type"),
    [
        ("goals.pdf", "application/pdf"),
        ("goals.pdf", "application/octet-stream"),
        (
            "goals.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("goals.docx", "application/octet-stream"),
    ],
)
def test_upload_validation_accepts_supported_file_types(file_name, content_type):
    _validate_upload(file_name, content_type, b"document")


def test_upload_validation_accepts_exact_maximum_size():
    _validate_upload(
        "goals.pdf",
        "application/pdf",
        b"x" * MAX_DOCUMENT_SIZE_BYTES,
    )


def test_upload_validation_rejects_mismatched_content_type():
    with pytest.raises(HTTPException) as error:
        _validate_upload("goals.pdf", "text/plain", b"document")

    assert error.value.status_code == 400
    assert "content type does not match" in error.value.detail


@pytest.mark.parametrize(
    ("url", "form_data"),
    [
        (
            "/documents",
            {"user_id": "user-1", "document_type": "goal"},
        ),
        (
            "/api/v1/documents/import",
            {"user_id": "user-1"},
        ),
    ],
)
def test_upload_routes_reject_files_over_maximum_size(url, form_data):
    service = MagicMock(spec=DocumentService)
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            url,
            data=form_data,
            files={
                "file": (
                    "goals.pdf",
                    b"x" * (MAX_DOCUMENT_SIZE_BYTES + 1),
                    "application/pdf",
                )
            },
        )

        assert response.status_code == 413
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


async def test_process_document():
    service = MagicMock(spec=DocumentService)
    service.process_document.return_value = _document(
        status=DocumentStatus.PROCESSED,
        extracted_content_path=(
            "storage/document-1/extracted.md"
        ),
    )

    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents/document-1/process",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "processed"
        assert data["extracted_content_path"] == (
            "storage/document-1/extracted.md"
        )
        assert "extracted_text" not in data
        service.process_document.assert_awaited_once_with(
            "document-1",
        )
    finally:
        app.dependency_overrides.clear()


async def test_process_document_returns_404_for_missing_document():
    service = MagicMock(spec=DocumentService)
    service.process_document.side_effect = ValueError(
        "Document not found."
    )

    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents/missing/process",
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found."
    finally:
        app.dependency_overrides.clear()


async def test_process_document_returns_422_for_extraction_failure():
    service = MagicMock(spec=DocumentService)
    service.process_document.side_effect = DocumentExtractionError(
        "Failed to extract text from document: goals.pdf"
    )

    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents/document-1/process",
        )

        assert response.status_code == 422
        assert "Failed to extract text" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


async def test_process_document_returns_422_for_classification_failure():
    service = MagicMock(spec=DocumentService)
    service.process_document.side_effect = DocumentClassificationError(
        "Document classification provider failed."
    )

    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/documents/document-1/process",
        )

        assert response.status_code == 422
        assert "classification provider failed" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
