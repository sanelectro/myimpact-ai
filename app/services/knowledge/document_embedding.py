from sqlalchemy.orm import Session

from app.models.embedding import EmbeddingRequest
from app.repositories.document_chunk import DocumentChunkRepository
from app.repositories.document_chunk_embedding import (
    DocumentChunkEmbeddingRepository,
)
from app.services.base import BaseService
from app.services.embedding.interface import IEmbeddingService


class DocumentChunkEmbeddingService(BaseService):
    """Generate and persist embeddings for all chunks in a document."""

    def __init__(
        self,
        session: Session,
        embedding_service: IEmbeddingService,
    ):
        super().__init__(session)
        self.chunk_repository = DocumentChunkRepository(session)
        self.embedding_repository = DocumentChunkEmbeddingRepository(session)
        self.embedding_service = embedding_service

    async def embed_document(self, document_id: str) -> int:
        chunks = self.chunk_repository.get_by_document_id(document_id)
        if not chunks:
            return 0

        response = await self.embedding_service.embed(
            EmbeddingRequest(inputs=[chunk.content for chunk in chunks])
        )

        if len(response.embeddings) != len(chunks):
            raise ValueError(
                "Embedding provider returned a different number of vectors "
                "than requested."
            )

        if not response.model:
            raise ValueError("Embedding provider must return an embedding model")

        try:
            for chunk, embedding in zip(
                chunks,
                response.embeddings,
                strict=True,
            ):
                self.embedding_repository.upsert(
                    chunk_id=chunk.id,
                    embedding=embedding,
                    embedding_model=response.model,
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return len(chunks)
