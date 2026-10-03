from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.document_chunk import DocumentChunkDB
from app.db.models.document_chunk_embedding import DocumentChunkEmbeddingDB
from app.repositories.base import BaseRepository


class DocumentChunkEmbeddingRepository(BaseRepository):
    """Persistence and vector retrieval for chunk embeddings."""

    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_chunk_id(
        self,
        chunk_id: str,
    ) -> DocumentChunkEmbeddingDB | None:
        return (
            self.session.query(DocumentChunkEmbeddingDB)
            .filter(DocumentChunkEmbeddingDB.chunk_id == chunk_id)
            .one_or_none()
        )

    def upsert(
        self,
        *,
        chunk_id: str,
        embedding: list[float],
        embedding_model: str,
    ) -> DocumentChunkEmbeddingDB:
        if not embedding:
            raise ValueError("Embedding must contain at least one value")

        now = datetime.now(UTC)
        existing = self.get_by_chunk_id(chunk_id)

        if existing is None:
            existing = DocumentChunkEmbeddingDB(
                id=str(uuid4()),
                chunk_id=chunk_id,
                embedding=embedding,
                embedding_model=embedding_model,
                embedding_dimensions=len(embedding),
                created_at=now,
                updated_at=now,
            )
            self.session.add(existing)
        else:
            existing.embedding = embedding
            existing.embedding_model = embedding_model
            existing.embedding_dimensions = len(embedding)
            existing.updated_at = now

        self.session.flush()
        return existing

    def delete_by_chunk_id(self, chunk_id: str) -> bool:
        embedding = self.get_by_chunk_id(chunk_id)
        if embedding is None:
            return False

        self.session.delete(embedding)
        self.session.flush()
        return True

    def delete_by_document_id(self, document_id: str) -> int:
        deleted = (
            self.session.query(DocumentChunkEmbeddingDB)
            .join(
                DocumentChunkDB,
                DocumentChunkDB.id == DocumentChunkEmbeddingDB.chunk_id,
            )
            .filter(DocumentChunkDB.document_id == document_id)
            .all()
        )

        for embedding in deleted:
            self.session.delete(embedding)

        self.session.flush()
        return len(deleted)

    def search_similar(
        self,
        *,
        query_embedding: list[float],
        embedding_model: str,
        limit: int = 5,
        document_id: str | None = None,
        user_id: str | None = None,
    ) -> list[tuple[DocumentChunkDB, float]]:
        if not query_embedding:
            raise ValueError("Query embedding must contain at least one value")
        if limit < 1:
            raise ValueError("Limit must be greater than zero")

        distance = DocumentChunkEmbeddingDB.embedding.cosine_distance(
            query_embedding
        )

        query = (
            self.session.query(DocumentChunkDB, distance.label("distance"))
            .join(
                DocumentChunkEmbeddingDB,
                DocumentChunkEmbeddingDB.chunk_id == DocumentChunkDB.id,
            )
            .filter(
                DocumentChunkEmbeddingDB.embedding_model == embedding_model,
                DocumentChunkEmbeddingDB.embedding_dimensions
                == len(query_embedding),
            )
        )

        if document_id is not None:
            query = query.filter(DocumentChunkDB.document_id == document_id)

        if user_id is not None:
            query = query.filter(DocumentChunkDB.document.has(user_id=user_id))

        rows = query.order_by(distance).limit(limit).all()

        return [
            (chunk, 1.0 - float(distance_value))
            for chunk, distance_value in rows
        ]
