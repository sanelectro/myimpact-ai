from datetime import date
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import DocumentStatus, DocumentType
from app.repositories.document import DocumentRepository


def test_get_by_id_returns_document():
    session = MagicMock(spec=Session)
    expected = MagicMock(spec=DocumentDB)
    session.get.return_value = expected

    repository = DocumentRepository(session)

    result = repository.get_by_id("document-1")

    assert result is expected
    session.get.assert_called_once_with(DocumentDB, "document-1")


def test_get_by_id_returns_none_when_not_found():
    session = MagicMock(spec=Session)
    session.get.return_value = None

    repository = DocumentRepository(session)

    assert repository.get_by_id("missing") is None
    session.get.assert_called_once_with(DocumentDB, "missing")


def test_get_by_user_id_returns_documents():
    session = MagicMock(spec=Session)
    document = MagicMock(spec=DocumentDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = [document]

    repository = DocumentRepository(session)

    result = repository.get_by_user_id("user-1")

    assert result == [document]
    session.query.assert_called_once_with(DocumentDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()


def test_get_by_user_and_type_returns_documents():
    session = MagicMock(spec=Session)
    document = MagicMock(spec=DocumentDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = [document]

    repository = DocumentRepository(session)

    result = repository.get_by_user_and_type(
        "user-1",
        DocumentType.GOAL,
    )

    assert result == [document]
    session.query.assert_called_once_with(DocumentDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()


def test_create_document():
    session = MagicMock(spec=Session)
    repository = DocumentRepository(session)

    result = repository.create(
        document_id="document-1",
        user_id="user-1",
        document_type=DocumentType.GOAL,
        file_name="goals.pdf",
        content_type="application/pdf",
        storage_path="documents/user-1/goals.pdf",
        source="employee_upload",
        effective_start=date(2026, 1, 1),
        effective_end=date(2026, 12, 31),
        content_hash="hash-1",
    )

    assert isinstance(result, DocumentDB)
    assert result.id == "document-1"
    assert result.user_id == "user-1"
    assert result.document_type == DocumentType.GOAL
    assert result.file_name == "goals.pdf"
    assert result.content_type == "application/pdf"
    assert result.storage_path == "documents/user-1/goals.pdf"
    assert result.source == "employee_upload"
    assert result.effective_start == date(2026, 1, 1)
    assert result.effective_end == date(2026, 12, 31)
    assert result.content_hash == "hash-1"
    assert result.status == DocumentStatus.UPLOADED
    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()


def test_create_document_with_minimum_fields():
    session = MagicMock(spec=Session)
    repository = DocumentRepository(session)

    result = repository.create(
        document_id="document-2",
        user_id="user-1",
        document_type=DocumentType.ONE_TO_ONE,
        file_name="one-to-one.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        storage_path="documents/user-1/one-to-one.docx",
    )

    assert isinstance(result, DocumentDB)
    assert result.source is None
    assert result.content_hash is None
    assert result.status == DocumentStatus.UPLOADED
    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()
