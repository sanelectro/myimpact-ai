from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.repositories.document_chunk_embedding import (
    DocumentChunkEmbeddingRepository,
)
from app.services.embedding.interface import IEmbeddingService
from app.models.embedding import EmbeddingRequest


class SemanticRetrievalService:
    """Generate a query embedding and retrieve semantically similar chunks."""

    def __init__(
        self,
        repository: DocumentChunkEmbeddingRepository,
        embedding_service: IEmbeddingService,
    ):
        self.repository = repository
        self.embedding_service = embedding_service

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        document_id: str | None = None,
        user_id: str | None = None,
    ) -> list[KnowledgeSearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("Query must not be empty")

        response = await self.embedding_service.embed(
            EmbeddingRequest(inputs=[query])
        )

        if len(response.embeddings) != 1:
            raise ValueError("Embedding provider must return one query vector")

        if not response.model:
            raise ValueError("Embedding provider must return an embedding model")

        rows = self.repository.search_similar(
            query_embedding=response.embeddings[0],
            embedding_model=response.model,
            limit=limit,
            document_id=document_id,
            user_id=user_id,
        )

        return [
            KnowledgeSearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                heading_path=chunk.heading_path,
                document_type=chunk.document_type.value,
                scope_type=chunk.scope_type.value,
                scope_id=chunk.scope_id,
                metadata=chunk.metadata_,
                similarity=similarity,
            )
            for chunk, similarity in rows
        ]
