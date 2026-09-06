from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.document import DocumentDB
from app.models.document import DocumentStatus, DocumentType
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
        source: str | None = None,
        effective_start=None,
        effective_end=None,
        content_hash: str | None = None,
        status: DocumentStatus = DocumentStatus.UPLOADED,
    ) -> DocumentDB:
        now = datetime.now(UTC)

        document = DocumentDB(
            id=document_id,
            user_id=user_id,
            document_type=document_type,
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
