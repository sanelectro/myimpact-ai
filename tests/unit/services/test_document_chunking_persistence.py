from unittest.mock import MagicMock, patch

from app.db.models.document import DocumentDB
from app.repositories.document_chunk import DocumentChunkRepository
from app.services.document import DocumentService
from app.services.document_chunking import DocumentChunkingService
from app.storage.interface import FileStorage
from app.models.document import DocumentScopeType, DocumentType
from sqlalchemy.orm import Session


def test_chunk_persistence_replaces_existing_chunks_after_successful_chunking():
    session = MagicMock(spec=Session)
    storage = MagicMock(spec=FileStorage)
    document = MagicMock(spec=DocumentDB)
    document.id = "document-1"
    document.extracted_content_path = "storage/extracted.md"
    document.classification_type = DocumentType.ROLE
    document.document_type = DocumentType.ONE_TO_ONE
    document.scope_type = DocumentScopeType.ROLE
    document.scope_id = "lead-engineer"

    storage.read.return_value = b"# Architecture\n\nDrive technical direction."

    service = DocumentService(
        session,
        storage=storage,
        chunking_service=DocumentChunkingService(),
    )
    repository = MagicMock(spec=DocumentChunkRepository)
    service.chunk_repository = repository

    with patch("app.services.document.uuid4", return_value="chunk-1"):
        service._chunk_and_persist_document(document)

    repository.delete_by_document_id.assert_called_once_with("document-1")
    repository.create.assert_called_once_with(
        chunk_id="chunk-1",
        document_id="document-1",
        chunk_index=0,
        content="Drive technical direction.",
        heading_path=["Architecture"],
        document_type=DocumentType.ROLE,
        scope_type=DocumentScopeType.ROLE,
        scope_id="lead-engineer",
        metadata={},
    )
    session.commit.assert_called_once()


def test_chunk_persistence_keeps_existing_chunks_when_chunking_fails():
    session = MagicMock(spec=Session)
    storage = MagicMock(spec=FileStorage)
    document = MagicMock(spec=DocumentDB)
    document.id = "document-1"
    document.extracted_content_path = "storage/extracted.md"

    storage.read.side_effect = UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")

    service = DocumentService(
        session,
        storage=storage,
        chunking_service=DocumentChunkingService(),
    )
    repository = MagicMock(spec=DocumentChunkRepository)
    service.chunk_repository = repository

    from app.exceptions import DocumentChunkingError

    try:
        service._chunk_and_persist_document(document)
    except DocumentChunkingError:
        pass
    else:
        raise AssertionError("Expected DocumentChunkingError")

    repository.delete_by_document_id.assert_not_called()
    repository.create.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
