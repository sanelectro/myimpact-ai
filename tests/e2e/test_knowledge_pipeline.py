from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.document_chunk import DocumentChunkDB
from app.db.models.document_chunk_embedding import DocumentChunkEmbeddingDB
from app.db.models.expectation import DocumentExpectationDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentClassification, DocumentType
from app.models.expectation import ExpectationExtractionResult
from app.models.user import UserCreate
from app.repositories.document_chunk import DocumentChunkRepository
from app.repositories.document_chunk_embedding import (
    DocumentChunkEmbeddingRepository,
)
from app.services.document import DocumentService
from app.services.document_chunking import DocumentChunkingService
from app.services.document_classification import DocumentClassificationService
from app.services.document_expectation import (
    DocumentExpectationExtractionService,
)
from app.services.embedding.mock_service import MockEmbeddingService
from app.services.knowledge.document_embedding import (
    DocumentChunkEmbeddingService,
)
from app.services.knowledge.semantic_retrieval import SemanticRetrievalService
from app.services.user import UserService
from app.storage.local import LocalFileStorage


@pytest.mark.integration
@pytest.mark.asyncio
async def test_knowledge_pipeline_end_to_end(tmp_path: Path):
    session = SessionLocal()

    user_id = None
    document_id = None

    try:
        # ---------------------------------------------------------
        # 1. Create test user
        # ---------------------------------------------------------
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Knowledge E2E User",
                email=f"{uuid4()}@example.com",
                role="Lead Software Engineer",
            )
        )

        user_id = user.id

        # ---------------------------------------------------------
        # 2. Configure document processing
        # ---------------------------------------------------------
        storage = LocalFileStorage(tmp_path)

        classification_service = AsyncMock(
            spec=DocumentClassificationService
        )
        classification_service.classify.return_value = DocumentClassification(
            document_type=DocumentType.DEVELOPMENT,
            confidence=0.98,
            reason="Contains engineering impact and technical leadership work.",
        )

        expectation_service = AsyncMock(
            spec=DocumentExpectationExtractionService
        )
        expectation_service.extract.return_value = (
            ExpectationExtractionResult(expectations=[])
        )

        chunking_service = DocumentChunkingService()

        document_service = DocumentService(
            session,
            storage=storage,
            classification_service=classification_service,
            expectation_extraction_service=expectation_service,
            chunking_service=chunking_service,
        )

        # ---------------------------------------------------------
        # 3. Load the demo document
        # ---------------------------------------------------------
        source_file = (
            Path(__file__).resolve().parents[2]
            / "demo-data"
            / "MyImpact_Demo_Lead_Engineer_Expectations.pdf"
        )

        assert source_file.exists()

        document = document_service.upload_document(
            user_id=user_id,
            document_type=DocumentType.DEVELOPMENT,
            file_name=source_file.name,
            content_type="application/pdf",
            content=source_file.read_bytes(),
        )

        document_id = document.id

        assert document.user_id == user_id
        assert document.status.value == "uploaded"
        assert storage.exists(document.storage_path)

        # ---------------------------------------------------------
        # 4. Process document
        #
        # PDF -> extraction -> classification ->
        # expectation extraction -> chunking
        # ---------------------------------------------------------
        processed_document = await document_service.process_document(
            document_id
        )

        assert processed_document.id == document_id
        assert processed_document.status.value == "processed"
        assert (
            processed_document.classification_type
            == DocumentType.DEVELOPMENT
        )
        assert processed_document.extracted_content_path
        assert storage.exists(processed_document.extracted_content_path)

        classification_service.classify.assert_awaited_once()
        expectation_service.extract.assert_awaited_once()

        # ---------------------------------------------------------
        # 5. Verify chunks
        # ---------------------------------------------------------
        chunks = DocumentChunkRepository(session).get_by_document_id(
            document_id
        )

        assert chunks
        assert len(chunks) > 0

        first_chunk = chunks[0]

        assert first_chunk.document_id == document_id
        assert first_chunk.content.strip()
        assert first_chunk.scope_id == user_id

        # ---------------------------------------------------------
        # 6. Generate and persist embeddings
        # ---------------------------------------------------------
        embedding_service = MockEmbeddingService(dimensions=8)

        embedding_indexer = DocumentChunkEmbeddingService(
            session,
            embedding_service,
        )

        embeddings_created = await embedding_indexer.embed_document(
            document_id
        )

        assert embeddings_created == len(chunks)

        # ---------------------------------------------------------
        # 7. Verify embeddings
        # ---------------------------------------------------------
        embedding_repository = DocumentChunkEmbeddingRepository(session)

        stored_embeddings = [
            embedding_repository.get_by_chunk_id(chunk.id)
            for chunk in chunks
        ]

        assert all(stored_embeddings)

        for embedding in stored_embeddings:
            assert embedding.embedding_model == "mock-embedding"
            assert embedding.embedding_dimensions == 8
            assert embedding.embedding is not None

        # ---------------------------------------------------------
        # 8. Semantic retrieval
        # ---------------------------------------------------------
        retrieval = SemanticRetrievalService(
            embedding_repository,
            embedding_service,
        )

        results = await retrieval.retrieve(
            first_chunk.content,
            user_id=user_id,
            limit=1,
        )

        # ---------------------------------------------------------
        # 9. Verify retrieved evidence
        # ---------------------------------------------------------
        assert len(results) == 1

        result = results[0]

        assert result.chunk_id == first_chunk.id
        assert result.document_id == document_id
        assert result.content == first_chunk.content
        assert result.scope_id == user_id
        assert result.similarity == pytest.approx(1.0)

    finally:
        # ---------------------------------------------------------
        # 10. Cleanup
        # ---------------------------------------------------------
        if document_id:
            session.execute(
                delete(DocumentChunkEmbeddingDB).where(
                    DocumentChunkEmbeddingDB.chunk_id.in_(
                        session.query(DocumentChunkDB.id).filter(
                            DocumentChunkDB.document_id == document_id
                        )
                    )
                )
            )

            session.execute(
                delete(DocumentChunkDB).where(
                    DocumentChunkDB.document_id == document_id
                )
            )

            session.execute(
                delete(DocumentExpectationDB).where(
                    DocumentExpectationDB.document_id == document_id
                )
            )

            session.execute(
                delete(DocumentDB).where(
                    DocumentDB.id == document_id
                )
            )

        if user_id:
            session.execute(
                delete(UserDB).where(
                    UserDB.id == user_id
                )
            )

        session.commit()
        session.close()