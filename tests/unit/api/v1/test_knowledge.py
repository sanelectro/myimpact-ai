from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.routes.document import MAX_DOCUMENT_SIZE_BYTES, get_document_service
from app.api.v1.knowledge import (
    MAX_EVIDENCE_FILE_SIZE_BYTES,
    get_retrieval_service,
)
from app.main import app
from app.models.document import DocumentScopeType, DocumentStatus, DocumentType
from app.models.document_chunk_embedding import KnowledgeSearchResult

client = TestClient(app)


def _document(user_id: str = "user-1", document_id: str = "doc-1"):
    document = MagicMock()
    document.id = document_id
    document.user_id = user_id
    document.file_name = "role.pdf"
    document.content_type = "application/pdf"
    document.document_type = DocumentType.ROLE
    document.scope_type = DocumentScopeType.EMPLOYEE
    document.scope_id = user_id
    document.status = DocumentStatus.PROCESSED
    document.classification_type = DocumentType.ROLE
    document.classification_confidence = 0.95
    document.created_at = __import__("datetime").datetime(2026, 1, 1)
    document.updated_at = __import__("datetime").datetime(2026, 1, 2)
    document.storage_path = "unused"
    return document


def test_knowledge_routes_are_mounted():
    response = client.get("/api/v1/knowledge/documents", params={"user_id": "user-1"})
    assert response.status_code != 404


def test_list_documents_returns_product_safe_contract():
    service = MagicMock()
    service.get_documents_by_user_id.return_value = [_document()]
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get("/api/v1/knowledge/documents", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == "doc-1"
    assert "storage_path" not in body[0]
    assert "user_id" not in body[0]


def test_upload_evidence_image_stores_file_without_processing():
    service = MagicMock()
    document = _document()
    document.document_type = DocumentType.PERSONAL_EVIDENCE
    service.upload_document.return_value = document
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents/evidence-files",
            data={"user_id": "user-1"},
            files={"file": ("proof.png", b"image-bytes", "image/png")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == "doc-1"
    service.upload_document.assert_called_once()
    assert service.upload_document.call_args.kwargs["document_type"] == DocumentType.PERSONAL_EVIDENCE
    assert service.upload_document.call_args.kwargs["content"] == b"image-bytes"


def test_upload_evidence_file_reuses_identical_file_for_same_user():
    service = MagicMock()
    existing = _document()
    existing.document_type = DocumentType.PERSONAL_EVIDENCE
    existing.content_hash = "2c8648d103e3dd7ad87660da0f126a1443b6d21ac1bd3ec000c5e24e2373a90c"
    service.get_documents_by_user_id.return_value = [existing]
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents/evidence-files",
            data={"user_id": "user-1"},
            files={"file": ("proof.png", b"image-bytes", "image/png")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["id"] == existing.id
    service.upload_document.assert_not_called()


def test_upload_evidence_file_rejects_unsupported_type():
    service = MagicMock()
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents/evidence-files",
            data={"user_id": "user-1"},
            files={"file": ("proof.exe", b"not-an-image", "application/octet-stream")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    service.upload_document.assert_not_called()


def test_upload_evidence_file_rejects_file_over_maximum_size():
    service = MagicMock()
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents/evidence-files",
            data={"user_id": "user-1"},
            files={
                "file": (
                    "proof.png",
                    b"x" * (MAX_EVIDENCE_FILE_SIZE_BYTES + 1),
                    "image/png",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
    service.upload_document.assert_not_called()


def test_upload_evidence_file_accepts_exact_maximum_size():
    service = MagicMock()
    document = _document()
    document.document_type = DocumentType.PERSONAL_EVIDENCE
    document.file_name = "proof.png"
    document.content_type = "image/png"
    service.get_documents_by_user_id.return_value = []
    service.upload_document.return_value = document
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents/evidence-files",
            data={"user_id": "user-1"},
            files={
                "file": (
                    "proof.png",
                    b"x" * MAX_EVIDENCE_FILE_SIZE_BYTES,
                    "image/png",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    service.upload_document.assert_called_once()


def test_upload_knowledge_document_rejects_file_over_maximum_size():
    service = MagicMock()
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents",
            data={"user_id": "user-1", "document_type": "goal"},
            files={
                "file": (
                    "goals.pdf",
                    b"x" * (MAX_DOCUMENT_SIZE_BYTES + 1),
                    "application/pdf",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
    service.upload_document.assert_not_called()


def test_upload_knowledge_document_processes_supported_docx():
    service = MagicMock()
    document = _document()
    document.document_type = DocumentType.GOAL
    document.file_name = "goals.docx"
    document.content_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    service.upload_document.return_value = document
    service.process_document = AsyncMock(return_value=document)
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents",
            data={"user_id": "user-1", "document_type": "goal"},
            files={
                "file": (
                    "goals.docx",
                    b"docx-bytes",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    service.upload_document.assert_called_once()
    service.process_document.assert_awaited_once_with(document.id)


@pytest.mark.parametrize(
    ("file_name", "content_type"),
    [
        ("proof.pdf", "application/pdf"),
        ("proof.pdf", "application/octet-stream"),
        ("proof.png", "image/png"),
        ("proof.png", "application/octet-stream"),
        ("proof.jpg", "image/jpeg"),
        ("proof.jpg", "application/octet-stream"),
        ("proof.jpeg", "image/jpeg"),
        ("proof.jpeg", "application/octet-stream"),
        ("proof.gif", "image/gif"),
        ("proof.gif", "application/octet-stream"),
        ("proof.webp", "image/webp"),
        ("proof.webp", "application/octet-stream"),
    ],
)
def test_upload_evidence_file_accepts_supported_type_and_mime(file_name, content_type):
    service = MagicMock()
    document = _document()
    document.document_type = DocumentType.PERSONAL_EVIDENCE
    document.file_name = file_name
    document.content_type = content_type
    service.get_documents_by_user_id.return_value = []
    service.upload_document.return_value = document
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents/evidence-files",
            data={"user_id": "user-1"},
            files={"file": (file_name, b"evidence", content_type)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    service.upload_document.assert_called_once()


def test_upload_evidence_file_rejects_mismatched_content_type():
    service = MagicMock()
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/documents/evidence-files",
            data={"user_id": "user-1"},
            files={"file": ("proof.png", b"not-an-image", "application/pdf")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    service.upload_document.assert_not_called()


def test_get_evidence_file_enforces_ownership_and_returns_content():
    service = MagicMock()
    document = _document(user_id="owner")
    document.document_type = DocumentType.PERSONAL_EVIDENCE
    service.get_document_by_id.return_value = document
    service.storage.read.return_value = b"proof"
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get(
            "/api/v1/knowledge/documents/doc-1/file",
            params={"user_id": "owner"},
        )
        denied = client.get(
            "/api/v1/knowledge/documents/doc-1/file",
            params={"user_id": "other-user"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"proof"
    assert response.headers["content-type"] == "application/pdf"
    assert denied.status_code == 404


def test_get_document_enforces_user_isolation():
    service = MagicMock()
    service.get_document_by_id.return_value = _document(user_id="owner")
    app.dependency_overrides[get_document_service] = lambda: service

    try:
        response = client.get(
            "/api/v1/knowledge/documents/doc-1",
            params={"user_id": "other-user"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_retrieve_knowledge_hides_similarity_and_embedding_details():
    service = MagicMock()
    service.retrieve = AsyncMock(
        return_value=[
            KnowledgeSearchResult(
                chunk_id="chunk-1",
                document_id="doc-1",
                content="Leads architecture decisions.",
                heading_path=["Responsibilities"],
                document_type="role",
                scope_type="employee",
                scope_id="user-1",
                metadata={"source_page": 2},
                similarity=0.98,
            )
        ]
    )
    app.dependency_overrides[get_retrieval_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/knowledge/retrieve",
            json={"query": "architecture leadership", "user_id": "user-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "document_id": "doc-1",
                "content": "Leads architecture decisions.",
                "heading_path": ["Responsibilities"],
                "document_type": "role",
                "scope_type": "employee",
                "scope_id": "user-1",
                "metadata": {"source_page": 2},
            }
        ]
    }
    service.retrieve.assert_awaited_once_with(
        "architecture leadership",
        limit=5,
        document_id=None,
        user_id="user-1",
    )
