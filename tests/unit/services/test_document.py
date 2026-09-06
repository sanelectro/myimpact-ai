from datetime import date
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import DocumentCreate, DocumentType
from app.repositories.document import DocumentRepository
from app.services.document import DocumentService
from app.storage.interface import FileStorage


def test_create_document():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    repository.create.return_value = MagicMock(spec=DocumentDB)

    service = DocumentService(session)
    service.repository = repository

    document_data = DocumentCreate(
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

    with patch(
        "app.services.document.uuid4",
        return_value="document-1",
    ):
        result = service.create_document(document_data)

    assert isinstance(result, DocumentDB)

    repository.create.assert_called_once_with(
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
    session.commit.assert_called_once()


def test_upload_document_saves_file_and_persists_metadata():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)

    expected = MagicMock(spec=DocumentDB)
    repository.create.return_value = expected
    storage.save.return_value = "/tmp/storage/user-1/document-1/goals.pdf"

    service = DocumentService(
        session,
        storage=storage,
    )
    service.repository = repository

    with patch(
        "app.services.document.uuid4",
        return_value="document-1",
    ):
        result = service.upload_document(
            user_id="user-1",
            document_type=DocumentType.GOAL,
            file_name="goals.pdf",
            content_type="application/pdf",
            content=b"annual goals",
        )

    assert result is expected

    storage.save.assert_called_once_with(
        user_id="user-1",
        document_id="document-1",
        file_name="goals.pdf",
        content=b"annual goals",
    )

    repository.create.assert_called_once()
    create_kwargs = repository.create.call_args.kwargs

    assert create_kwargs["document_id"] == "document-1"
    assert create_kwargs["user_id"] == "user-1"
    assert create_kwargs["document_type"] == DocumentType.GOAL
    assert create_kwargs["file_name"] == "goals.pdf"
    assert create_kwargs["content_type"] == "application/pdf"
    assert create_kwargs["storage_path"] == "/tmp/storage/user-1/document-1/goals.pdf"
    assert create_kwargs["source"] == "employee_upload"
    assert len(create_kwargs["content_hash"]) == 64

    session.commit.assert_called_once()


def test_upload_document_rolls_back_and_removes_file_when_persistence_fails():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)

    storage_path = "/tmp/storage/user-1/document-1/goals.pdf"
    storage.save.return_value = storage_path
    storage.exists.return_value = True
    repository.create.side_effect = RuntimeError("database failure")

    service = DocumentService(
        session,
        storage=storage,
    )
    service.repository = repository

    with patch(
        "app.services.document.uuid4",
        return_value="document-1",
    ):
        try:
            service.upload_document(
                user_id="user-1",
                document_type=DocumentType.GOAL,
                file_name="goals.pdf",
                content_type="application/pdf",
                content=b"annual goals",
            )
        except RuntimeError as exc:
            assert str(exc) == "database failure"
        else:
            raise AssertionError("Expected RuntimeError")

    session.rollback.assert_called_once()
    storage.exists.assert_called_once_with(storage_path)
    storage.delete.assert_called_once_with(storage_path)
    session.commit.assert_not_called()


def test_get_document_by_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    expected = MagicMock(spec=DocumentDB)
    repository.get_by_id.return_value = expected

    service = DocumentService(session)
    service.repository = repository

    assert service.get_document_by_id("document-1") is expected
    repository.get_by_id.assert_called_once_with("document-1")


def test_get_documents_by_user_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    expected = [MagicMock(spec=DocumentDB)]
    repository.get_by_user_id.return_value = expected

    service = DocumentService(session)
    service.repository = repository

    assert service.get_documents_by_user_id("user-1") == expected
    repository.get_by_user_id.assert_called_once_with("user-1")


def test_get_documents_by_user_and_type():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    expected = [MagicMock(spec=DocumentDB)]
    repository.get_by_user_and_type.return_value = expected

    service = DocumentService(session)
    service.repository = repository

    assert service.get_documents_by_user_and_type(
        "user-1",
        DocumentType.ONE_TO_ONE,
    ) == expected
    repository.get_by_user_and_type.assert_called_once_with(
        "user-1",
        DocumentType.ONE_TO_ONE,
    )
    session.commit.assert_not_called()
