from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.document_chunk import DocumentChunkDB
from app.models.document import DocumentScopeType, DocumentType
from app.repositories.base import BaseRepository


class DocumentChunkRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, chunk_id: str) -> DocumentChunkDB | None:
        return self.session.get(DocumentChunkDB, chunk_id)

    def get_by_document_id(self, document_id: str) -> list[DocumentChunkDB]:
        return (
            self.session.query(DocumentChunkDB)
            .filter(DocumentChunkDB.document_id == document_id)
            .order_by(DocumentChunkDB.chunk_index)
            .all()
        )

    def create(
        self,
        *,
        chunk_id: str,
        document_id: str,
        chunk_index: int,
        content: str,
        heading_path: list[str],
        document_type: DocumentType,
        scope_type: DocumentScopeType,
        scope_id: str | None,
        metadata: dict[str, Any],
    ) -> DocumentChunkDB:
        now = datetime.now(UTC)

        chunk = DocumentChunkDB(
            id=chunk_id,
            document_id=document_id,
            chunk_index=chunk_index,
            content=content,
            heading_path=heading_path,
            document_type=document_type,
            scope_type=scope_type,
            scope_id=scope_id,
            metadata_=metadata,
            created_at=now,
            updated_at=now,
        )

        self.session.add(chunk)
        self.session.flush()

        return chunk

    def delete_by_document_id(self, document_id: str) -> int:
        chunks = (
            self.session.query(DocumentChunkDB)
            .filter(DocumentChunkDB.document_id == document_id)
            .all()
        )

        for chunk in chunks:
            self.session.delete(chunk)

        self.session.flush()
        return len(chunks)