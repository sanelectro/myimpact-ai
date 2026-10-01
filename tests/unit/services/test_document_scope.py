from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import DocumentScopeType, DocumentType
from app.repositories.document import DocumentRepository
from app.services.document import DocumentService
from app.storage.interface import FileStorage


def test_create_role_scoped_document():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    repository.create.return_value = MagicMock(spec=DocumentDB)

    service = DocumentService(session)
    service.repository = repository

    from app.models.document import DocumentCreate

    document_data = DocumentCreate(
        user_id="admin-1",
        document_type=DocumentType.ROLE,
        scope_type=DocumentScopeType.ROLE,
        scope_id="lead_engineer",
        file_name="lead-engineer-role.pdf",
        content_type="application/pdf",
        storage_path="documents/lead-engineer-role.pdf",
    )

    with patch(
        "app.services.document.uuid4",
        return_value="document-1",
    ):
        service.create_document(document_data)

    repository.create.assert_called_once_with(
        document_id="document-1",
        user_id="admin-1",
        document_type=DocumentType.ROLE,
        scope_type=DocumentScopeType.ROLE,
        scope_id="lead_engineer",
        file_name="lead-engineer-role.pdf",
        content_type="application/pdf",
        storage_path="documents/lead-engineer-role.pdf",
        source=None,
        effective_start=None,
        effective_end=None,
        content_hash=None,
    )


def test_get_documents_by_scope():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    expected = [MagicMock(spec=DocumentDB)]
    repository.get_by_scope.return_value = expected

    service = DocumentService(session)
    service.repository = repository

    result = service.get_documents_by_scope(
        DocumentScopeType.ROLE,
        "lead_engineer",
    )

    assert result == expected
    repository.get_by_scope.assert_called_once_with(
        DocumentScopeType.ROLE,
        "lead_engineer",
    )


def test_upload_role_document_requires_scope_id():
    session = MagicMock(spec=Session)
    storage = MagicMock(spec=FileStorage)

    service = DocumentService(
        session,
        storage=storage,
    )

    with pytest.raises(
        ValueError,
        match="Role documents require a scope_id",
    ):
        service.upload_document(
            user_id="admin-1",
            document_type=DocumentType.ROLE,
            scope_type=DocumentScopeType.ROLE,
            scope_id=None,
            file_name="lead-engineer-role.pdf",
            content_type="application/pdf",
            content=b"role",
        )
