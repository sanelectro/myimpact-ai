from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.document_processing.factory import TextExtractorFactory
from app.exceptions import DocumentClassificationError, DocumentExtractionError
from app.models.document import (
    DocumentClassification,
    DocumentCreate,
    DocumentScopeType,
    DocumentStatus,
    DocumentType,
)
from app.repositories.document import DocumentRepository
from app.services.document import (
    EXTRACTED_CONTENT_FILE_NAME,
    DocumentService,
)
from app.services.document_classification import DocumentClassificationService
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
        scope_type=DocumentScopeType.EMPLOYEE,
        scope_id="user-1",
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

    create_kwargs = repository.create.call_args.kwargs
    assert create_kwargs["document_id"] == "document-1"
    assert create_kwargs["scope_type"] == DocumentScopeType.EMPLOYEE
    assert create_kwargs["scope_id"] == "user-1"
    assert create_kwargs["storage_path"] == (
        "/tmp/storage/user-1/document-1/goals.pdf"
    )
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
    ), pytest.raises(RuntimeError, match="database failure"):
        service.upload_document(
            user_id="user-1",
            document_type=DocumentType.GOAL,
            file_name="goals.pdf",
            content_type="application/pdf",
            content=b"annual goals",
        )

    session.rollback.assert_called_once()
    storage.exists.assert_called_once_with(storage_path)
    storage.delete.assert_called_once_with(storage_path)
    session.commit.assert_not_called()


def test_process_document_extracts_and_persists_markdown_file():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)

    document = MagicMock(spec=DocumentDB)
    document.id = "document-1"
    document.user_id = "user-1"
    document.file_name = "goals.pdf"
    document.storage_path = "storage/goals.pdf"

    processed_document = MagicMock(spec=DocumentDB)
    repository.get_by_id.return_value = document
    repository.update_processing.return_value = processed_document
    storage.read.return_value = b"pdf-content"
    storage.save.return_value = "storage/extracted.md"

    extractor = MagicMock()
    extractor.extract.return_value = (
        "# 2026 Goals\n\nImprove reliability."
    )

    service = DocumentService(
        session,
        storage=storage,
    )
    service.repository = repository

    with patch.object(
        TextExtractorFactory,
        "create",
        return_value=extractor,
    ):
        result = service.process_document("document-1")

    assert result is processed_document
    storage.read.assert_called_once_with("storage/goals.pdf")
    extractor.extract.assert_called_once_with(
        b"pdf-content",
        "goals.pdf",
    )
    storage.save.assert_called_once_with(
        user_id="user-1",
        document_id="document-1",
        file_name=EXTRACTED_CONTENT_FILE_NAME,
        content=b"# 2026 Goals\n\nImprove reliability.",
    )
    repository.update_processing.assert_called_once_with(
        document_id="document-1",
        extracted_content_path="storage/extracted.md",
        status=DocumentStatus.PROCESSED,
    )
    session.commit.assert_called_once()


def test_process_document_marks_failed_when_extraction_fails():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)

    document = MagicMock(spec=DocumentDB)
    document.file_name = "goals.pdf"
    document.storage_path = "storage/goals.pdf"

    repository.get_by_id.return_value = document
    storage.read.return_value = b"bad-document"

    extractor = MagicMock()
    extractor.extract.side_effect = DocumentExtractionError(
        "Failed to extract text from document: goals.pdf"
    )

    service = DocumentService(
        session,
        storage=storage,
    )
    service.repository = repository

    with patch.object(
        TextExtractorFactory,
        "create",
        return_value=extractor,
    ), pytest.raises(DocumentExtractionError):
        service.process_document("document-1")

    repository.update_processing.assert_called_once_with(
        document_id="document-1",
        extracted_content_path=None,
        status=DocumentStatus.FAILED,
    )
    storage.save.assert_not_called()
    session.commit.assert_called_once()


def test_process_document_raises_for_missing_document():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)

    repository.get_by_id.return_value = None

    service = DocumentService(
        session,
        storage=storage,
    )
    service.repository = repository

    with pytest.raises(ValueError, match="Document not found"):
        service.process_document("missing")

    storage.read.assert_not_called()
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


async def test_classify_document_persists_result():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)
    classification_service = AsyncMock(
        spec=DocumentClassificationService
    )

    document = MagicMock(spec=DocumentDB)
    document.extracted_content_path = "storage/extracted.md"
    classified_document = MagicMock(spec=DocumentDB)
    repository.get_by_id.return_value = document
    repository.update_classification.return_value = classified_document
    storage.read.return_value = b"# Annual Goals\nImprove reliability."
    classification_service.classify.return_value = DocumentClassification(
        document_type=DocumentType.GOAL,
        confidence=0.94,
        reason="Contains annual objectives.",
    )

    service = DocumentService(
        session,
        storage=storage,
        classification_service=classification_service,
    )
    service.repository = repository

    result = await service.classify_document("document-1")

    assert result is classified_document
    storage.read.assert_called_once_with("storage/extracted.md")
    classification_service.classify.assert_awaited_once_with(
        "# Annual Goals\nImprove reliability."
    )
    repository.update_classification.assert_called_once_with(
        document_id="document-1",
        classification_type=DocumentType.GOAL,
        classification_confidence=0.94,
        classification_reason="Contains annual objectives.",
        classification_error=None,
    )
    session.commit.assert_called_once()


async def test_classify_document_persists_safe_failure():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)
    classification_service = AsyncMock(
        spec=DocumentClassificationService
    )

    document = MagicMock(spec=DocumentDB)
    document.extracted_content_path = "storage/extracted.md"
    repository.get_by_id.return_value = document
    repository.update_classification.return_value = document
    storage.read.return_value = b"Annual goals"
    classification_service.classify.side_effect = (
        DocumentClassificationError(
            "Document classification provider failed."
        )
    )

    service = DocumentService(
        session,
        storage=storage,
        classification_service=classification_service,
    )
    service.repository = repository

    with pytest.raises(
        DocumentClassificationError,
        match="provider failed",
    ):
        await service.classify_document("document-1")

    repository.update_classification.assert_called_once_with(
        document_id="document-1",
        classification_type=None,
        classification_confidence=None,
        classification_reason=None,
        classification_error="Document classification provider failed.",
    )
    session.commit.assert_called_once()


async def test_classify_document_requires_processed_content():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    storage = MagicMock(spec=FileStorage)
    classification_service = AsyncMock(
        spec=DocumentClassificationService
    )

    document = MagicMock(spec=DocumentDB)
    document.extracted_content_path = None
    repository.get_by_id.return_value = document

    service = DocumentService(
        session,
        storage=storage,
        classification_service=classification_service,
    )
    service.repository = repository

    with pytest.raises(
        DocumentClassificationError,
        match="processed before classification",
    ):
        await service.classify_document("document-1")

    classification_service.classify.assert_not_awaited()
    repository.update_classification.assert_not_called()
    session.commit.assert_not_called()


def test_get_documents_by_user_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=DocumentRepository)
    expected = [MagicMock(spec=DocumentDB)]
    repository.get_by_user_id.return_value = expected

    service = DocumentService(session)
    service.repository = repository

    assert service.get_documents_by_user_id("user-1") == expected
    repository.get_by_user_id.assert_called_once_with("user-1")
    session.commit.assert_not_called()


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
