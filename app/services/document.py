import hashlib
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.document_processing.factory import TextExtractorFactory
from app.exceptions import (
    DocumentClassificationError,
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
from app.services.base import BaseService
from app.services.document_classification import DocumentClassificationService
from app.storage.interface import FileStorage

logger = logging.getLogger(__name__)

EXTRACTED_CONTENT_FILE_NAME = "extracted.md"


class DocumentService(BaseService):
    def __init__(
        self,
        session: Session,
        storage: FileStorage | None = None,
        classification_service: DocumentClassificationService | None = None,
    ):
        super().__init__(session)
        self.repository = DocumentRepository(session)
        self.storage = storage
        self.classification_service = classification_service

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

        return await self._classify_document(processed_document)

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

    def get_document_by_id(
        self,
        document_id: str,
    ) -> DocumentDB | None:
        return self.repository.get_by_id(document_id)

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
