from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.routes.document import get_document_service
from app.api.v1.knowledge import get_retrieval_service
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
