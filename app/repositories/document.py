from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import (
    DocumentScopeType,
    DocumentStatus,
    DocumentType,
)
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, document_id: str) -> DocumentDB | None:
        return self.session.get(DocumentDB, document_id)

    def get_by_user_id(self, user_id: str) -> list[DocumentDB]:
        return (
            self.session.query(DocumentDB)
            .filter(DocumentDB.user_id == user_id)
            .all()
        )

    def get_by_scope(
        self,
        scope_type: DocumentScopeType,
        scope_id: str | None,
    ) -> list[DocumentDB]:
        return (
            self.session.query(DocumentDB)
            .filter(
                DocumentDB.scope_type == scope_type,
                DocumentDB.scope_id == scope_id,
            )
            .all()
        )

    def get_by_user_and_type(
        self,
        user_id: str,
        document_type: DocumentType,
    ) -> list[DocumentDB]:
        return (
            self.session.query(DocumentDB)
            .filter(
                DocumentDB.user_id == user_id,
                DocumentDB.document_type == document_type,
            )
            .all()
        )

    def create(
        self,
        *,
        document_id: str,
        user_id: str,
        document_type: DocumentType,
        file_name: str,
        content_type: str,
        storage_path: str,
        scope_type: DocumentScopeType = DocumentScopeType.EMPLOYEE,
        scope_id: str | None = None,
        source: str | None = None,
        effective_start=None,
        effective_end=None,
        content_hash: str | None = None,
        status: DocumentStatus = DocumentStatus.UPLOADED,
    ) -> DocumentDB:
        now = datetime.now(UTC)

        if (
            scope_type == DocumentScopeType.EMPLOYEE
            and scope_id is None
        ):
            scope_id = user_id

        document = DocumentDB(
            id=document_id,
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
            status=status,
            created_at=now,
            updated_at=now,
        )

        self.session.add(document)
        self.session.flush()

        return document

    def update_processing(
        self,
        *,
        document_id: str,
        extracted_content_path: str | None,
        status: DocumentStatus,
    ) -> DocumentDB | None:
        document = self.session.get(DocumentDB, document_id)

        if document is None:
            return None

        document.extracted_content_path = extracted_content_path
        document.status = status
        document.updated_at = datetime.now(UTC)

        self.session.flush()

        return document

    def update_classification(
        self,
        *,
        document_id: str,
        classification_type: DocumentType | None,
        classification_confidence: float | None,
        classification_reason: str | None,
        classification_error: str | None,
    ) -> DocumentDB | None:
        document = self.session.get(DocumentDB, document_id)

        if document is None:
            return None

        now = datetime.now(UTC)
        document.classification_type = classification_type
        document.classification_confidence = classification_confidence
        document.classification_reason = classification_reason
        document.classification_error = classification_error
        document.classified_at = now
        document.updated_at = now

        self.session.flush()

        return document
