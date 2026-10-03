import hashlib
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.document_processing.factory import TextExtractorFactory
from app.exceptions import (
    DocumentChunkingError,
    DocumentClassificationError,
    DocumentExpectationExtractionError,
    DocumentExtractionError,
    StorageFileNotFoundError,
)
from app.models.document import (
    DocumentCreate,
    DocumentScopeType,
    DocumentStatus,
    DocumentType,
)
from app.repositories.document import DocumentRepository
from app.repositories.document_chunk import DocumentChunkRepository
from app.repositories.expectation import DocumentExpectationRepository
from app.services.base import BaseService
from app.services.document_classification import DocumentClassificationService
from app.services.document_expectation import (
    DocumentExpectationExtractionService,
)
from app.services.document_chunking import DocumentChunkingService
from app.storage.interface import FileStorage

logger = logging.getLogger(__name__)

EXTRACTED_CONTENT_FILE_NAME = "extracted.md"


class DocumentService(BaseService):
    def __init__(
        self,
        session: Session,
        storage: FileStorage | None = None,
        classification_service: DocumentClassificationService | None = None,
        expectation_extraction_service: (
            DocumentExpectationExtractionService | None
        ) = None,
        chunking_service: DocumentChunkingService | None = None,
    ):
        super().__init__(session)
        self.repository = DocumentRepository(session)
        self.storage = storage
        self.classification_service = classification_service
        self.expectation_extraction_service = expectation_extraction_service
        self.expectation_repository = DocumentExpectationRepository(session)
        self.chunk_repository = DocumentChunkRepository(session)
        self.chunking_service = chunking_service

    def create_document(
        self,
        document_data: DocumentCreate,
    ) -> DocumentDB:
        document = self.repository.create(
            document_id=str(uuid4()),
            user_id=document_data.user_id,
            document_type=document_data.document_type,
            scope_type=document_data.scope_type,
            scope_id=document_data.scope_id,
            file_name=document_data.file_name,
            content_type=document_data.content_type,
            storage_path=document_data.storage_path,
            source=document_data.source,
            effective_start=document_data.effective_start,
            effective_end=document_data.effective_end,
            content_hash=document_data.content_hash,
        )

        self.commit()

        return document

    def upload_document(
        self,
        *,
        user_id: str,
        document_type: DocumentType,
        file_name: str,
        content_type: str,
        content: bytes,
        scope_type: DocumentScopeType = DocumentScopeType.EMPLOYEE,
        scope_id: str | None = None,
        source: str = "employee_upload",
        effective_start=None,
        effective_end=None,
    ) -> DocumentDB:
        if self.storage is None:
            raise RuntimeError("File storage is not configured.")

        if scope_type == DocumentScopeType.EMPLOYEE:
            if scope_id is None:
                scope_id = user_id
            elif scope_id != user_id:
                raise ValueError(
                    "Employee document scope_id must match user_id."
                )

        elif scope_type == DocumentScopeType.ROLE:
            if not scope_id:
                raise ValueError(
                    "Role documents require a scope_id."
                )

        elif scope_id is not None:
            raise ValueError(
                "Global documents must not have a scope_id."
            )

        document_id = str(uuid4())
        content_hash = hashlib.sha256(content).hexdigest()

        storage_path = self.storage.save(
            user_id=user_id,
            document_id=document_id,
            file_name=file_name,
            content=content,
        )

        try:
            document = self.repository.create(
                document_id=document_id,
                user_id=user_id,
                document_type=document_type,
                scope_type=scope_type,
                scope_id=scope_id,
                file_name=file_name,
                content_type=content_type,
                storage_path=storage_path,
                source=source,
                effective_start=effective_start,
                effective_end=effective_end,
                content_hash=content_hash,
            )

            self.commit()

            return document

        except Exception:
            self.session.rollback()

            try:
                if self.storage.exists(storage_path):
                    self.storage.delete(storage_path)
            except (OSError, ValueError):
                logger.warning(
                    "Failed to clean up stored file %s after persistence "
                    "failure.",
                    storage_path,
                    exc_info=True,
                )

            raise

    async def process_document(
        self,
        document_id: str,
    ) -> DocumentDB:
        if self.storage is None:
            raise RuntimeError("File storage is not configured.")

        document = self.repository.get_by_id(document_id)

        if document is None:
            raise ValueError("Document not found.")

        try:
            content = self.storage.read(document.storage_path)
            extractor = TextExtractorFactory.create(document.file_name)
            markdown = extractor.extract(
                content,
                document.file_name,
            )
        except DocumentExtractionError:
            self.repository.update_processing(
                document_id=document_id,
                extracted_content_path=None,
                status=DocumentStatus.FAILED,
            )
            self.commit()
            raise

        extracted_content_path = self.storage.save(
            user_id=document.user_id,
            document_id=document.id,
            file_name=EXTRACTED_CONTENT_FILE_NAME,
            content=markdown.encode("utf-8"),
        )

        try:
            processed_document = self.repository.update_processing(
                document_id=document_id,
                extracted_content_path=extracted_content_path,
                status=DocumentStatus.PROCESSED,
            )

            if processed_document is None:
                raise ValueError("Document not found.")

            self.commit()

        except Exception:
            self.session.rollback()

            try:
                if self.storage.exists(extracted_content_path):
                    self.storage.delete(extracted_content_path)
            except (OSError, ValueError):
                logger.warning(
                    "Failed to clean up extracted content %s after "
                    "persistence failure.",
                    extracted_content_path,
                    exc_info=True,
                )

            raise

        classified_document = await self._classify_document(processed_document)

        if self.expectation_extraction_service is not None:
            processed_document = await self._extract_and_persist_expectations(
                classified_document
            )
        else:
            processed_document = classified_document

        if self.chunking_service is not None:
            self._chunk_and_persist_document(processed_document)

        return processed_document

    async def _classify_document(
        self,
        document: DocumentDB,
    ) -> DocumentDB:
        if self.storage is None:
            raise RuntimeError("File storage is not configured.")

        if self.classification_service is None:
            raise RuntimeError(
                "Document classification service is not configured."
            )

        if not document.extracted_content_path:
            raise DocumentClassificationError(
                "Document must be processed before classification."
            )

        try:
            content = self.storage.read(
                document.extracted_content_path
            ).decode("utf-8")
            classification = await self.classification_service.classify(
                content
            )
        except DocumentClassificationError as exc:
            self._persist_classification_failure(
                document.id,
                str(exc),
            )
            raise
        except (StorageFileNotFoundError, UnicodeDecodeError) as exc:
            error = DocumentClassificationError(
                "Extracted document content could not be read."
            )
            self._persist_classification_failure(
                document.id,
                str(error),
            )
            raise error from exc

        classified_document = self.repository.update_classification(
            document_id=document.id,
            classification_type=classification.document_type,
            classification_confidence=classification.confidence,
            classification_reason=classification.reason,
            classification_error=None,
        )

        if classified_document is None:
            raise ValueError("Document not found.")

        self.commit()
        return classified_document

    async def _extract_and_persist_expectations(
        self,
        document: DocumentDB,
    ) -> DocumentDB:
        if self.storage is None:
            raise RuntimeError("File storage is not configured.")

        if self.expectation_extraction_service is None:
            return document

        if not document.extracted_content_path:
            raise DocumentExpectationExtractionError(
                "Document must be processed before expectation extraction."
            )

        try:
            content = self.storage.read(
                document.extracted_content_path
            ).decode("utf-8")
            extraction_result = (
                await self.expectation_extraction_service.extract(content)
            )
        except DocumentExpectationExtractionError:
            raise
        except (StorageFileNotFoundError, UnicodeDecodeError) as exc:
            raise DocumentExpectationExtractionError(
                "Extracted document content could not be read for "
                "expectation extraction."
            ) from exc

        try:
            self.expectation_repository.delete_by_document_id(document.id)

            for expectation in extraction_result.expectations:
                source_reference = expectation.source_reference
                self.expectation_repository.create(
                    expectation_id=str(uuid4()),
                    document_id=document.id,
                    category=expectation.category,
                    description=expectation.description,
                    evidence_hints=expectation.evidence_hints,
                    source_page=(
                        source_reference.page
                        if source_reference is not None
                        else None
                    ),
                    source_section=(
                        source_reference.section
                        if source_reference is not None
                        else None
                    ),
                    source_text_span=(
                        source_reference.text_span
                        if source_reference is not None
                        else None
                    ),
                    confidence=expectation.confidence,
                )

            self.commit()
        except Exception:
            self.session.rollback()
            raise

        return document


    def _chunk_and_persist_document(
        self,
        document: DocumentDB,
    ) -> None:
        if self.storage is None:
            raise RuntimeError("File storage is not configured.")

        if self.chunking_service is None:
            return

        if not document.extracted_content_path:
            raise DocumentChunkingError(
                "Document must be processed before chunking."
            )

        try:
            content = self.storage.read(
                document.extracted_content_path
            ).decode("utf-8")
            chunk_contents = self.chunking_service.chunk(content)
        except (StorageFileNotFoundError, UnicodeDecodeError, ValueError) as exc:
            raise DocumentChunkingError(
                "Extracted document content could not be chunked."
            ) from exc

        try:
            self.chunk_repository.delete_by_document_id(document.id)

            for chunk_index, chunk_content in enumerate(chunk_contents):
                self.chunk_repository.create(
                    chunk_id=str(uuid4()),
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=chunk_content.content,
                    heading_path=chunk_content.heading_path,
                    document_type=(
                        document.classification_type or document.document_type
                    ),
                    scope_type=document.scope_type,
                    scope_id=document.scope_id,
                    metadata={},
                )

            self.commit()
        except Exception:
            self.session.rollback()
            raise

    def get_document_by_id(
        self,
        document_id: str,
    ) -> DocumentDB | None:
        return self.repository.get_by_id(document_id)

    def get_document_expectations(
        self,
        document_id: str,
    ):
        return self.expectation_repository.get_by_document_id(document_id)

    def _persist_classification_failure(
        self,
        document_id: str,
        error: str,
    ) -> None:
        self.repository.update_classification(
            document_id=document_id,
            classification_type=None,
            classification_confidence=None,
            classification_reason=None,
            classification_error=error,
        )
        self.commit()

    def get_documents_by_user_id(
        self,
        user_id: str,
    ) -> list[DocumentDB]:
        return self.repository.get_by_user_id(user_id)

    def get_documents_by_scope(
        self,
        scope_type: DocumentScopeType,
        scope_id: str | None,
    ) -> list[DocumentDB]:
        return self.repository.get_by_scope(
            scope_type,
            scope_id,
        )

    def get_documents_by_user_and_type(
        self,
        user_id: str,
        document_type: DocumentType,
    ) -> list[DocumentDB]:
        return self.repository.get_by_user_and_type(
            user_id,
            document_type,
        )
