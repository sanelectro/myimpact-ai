import hashlib
import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import DocumentCreate, DocumentType
from app.repositories.document import DocumentRepository
from app.services.base import BaseService
from app.storage.interface import FileStorage

logger = logging.getLogger(__name__)


class DocumentService(BaseService):
    def __init__(
        self,
        session: Session,
        storage: FileStorage | None = None,
    ):
        super().__init__(session)
        self.repository = DocumentRepository(session)
        self.storage = storage

    def create_document(
        self,
        document_data: DocumentCreate,
    ) -> DocumentDB:
        document = self.repository.create(
            document_id=str(uuid4()),
            user_id=document_data.user_id,
            document_type=document_data.document_type,
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
        source: str = "employee_upload",
        effective_start=None,
        effective_end=None,
    ) -> DocumentDB:
        if self.storage is None:
            raise RuntimeError("File storage is not configured.")

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
            except (OSError, ValueError) as cleanup_error:
                logger.warning(
                    "Failed to clean up stored file %s after persistence "
                    "failure: %s",
                    storage_path,
                    cleanup_error,
                    exc_info=True,
                )

            raise

    def get_document_by_id(
        self,
        document_id: str,
    ) -> DocumentDB | None:
        return self.repository.get_by_id(document_id)

    def get_documents_by_user_id(
        self,
        user_id: str,
    ) -> list[DocumentDB]:
        return self.repository.get_by_user_id(user_id)

    def get_documents_by_user_and_type(
        self,
        user_id: str,
        document_type: DocumentType,
    ) -> list[DocumentDB]:
        return self.repository.get_by_user_and_type(
            user_id,
            document_type,
        )