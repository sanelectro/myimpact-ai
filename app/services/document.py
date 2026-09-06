from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import DocumentCreate, DocumentType
from app.repositories.document import DocumentRepository
from app.services.base import BaseService


class DocumentService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = DocumentRepository(session)

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
