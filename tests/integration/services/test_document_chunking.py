from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.document_chunk import DocumentChunkDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentClassification, DocumentType
from app.models.user import UserCreate
from app.services.document import DocumentService
from app.services.document_classification import DocumentClassificationService
from app.services.document_chunking import DocumentChunkingService
from app.services.user import UserService
from app.storage.local import LocalFileStorage


@pytest.mark.integration
async def test_document_processing_persists_heading_aware_chunks(tmp_path: Path):
    session = SessionLocal()
    user_id = None
    document_id = None
    storage = LocalFileStorage(tmp_path)

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M3 Chunking User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        from unittest.mock import AsyncMock

        classification_service = AsyncMock(
            spec=DocumentClassificationService
        )
        classification_service.classify.return_value = DocumentClassification(
            document_type=DocumentType.ONE_TO_ONE,
            confidence=0.95,
            reason="Engineering discussion.",
        )

        service = DocumentService(
            session,
            storage=storage,
            classification_service=classification_service,
            chunking_service=DocumentChunkingService(),
        )

        document = service.upload_document(
            user_id=user_id,
            document_type=DocumentType.ONE_TO_ONE,
            file_name="knowledge.pdf",
            content_type="application/pdf",
            content=b"not used by mocked extractor",
        )
        document_id = document.id
        document.extracted_content_path = storage.save(
            user_id=user_id,
            document_id=document.id,
            file_name="extracted.md",
            content=(
                "# Engineering Expectations\n\n"
                "Context.\n\n"
                "## Technical Leadership\n\n"
                "Drive architecture decisions.\n\n"
                "### Architecture\n\n"
                "Create clear technical direction."
            ).encode(),
        )
        session.commit()

        # Directly exercise the persistence stage using normalized Markdown.
        await service._classify_document(document)
        service._chunk_and_persist_document(document)

        chunks = (
            session.query(DocumentChunkDB)
            .filter(DocumentChunkDB.document_id == document.id)
            .order_by(DocumentChunkDB.chunk_index)
            .all()
        )

        assert len(chunks) == 3
        assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
        assert [chunk.heading_path for chunk in chunks] == [
            ["Engineering Expectations"],
            ["Engineering Expectations", "Technical Leadership"],
            [
                "Engineering Expectations",
                "Technical Leadership",
                "Architecture",
            ],
        ]
        assert [chunk.content for chunk in chunks] == [
            "Context.",
            "Drive architecture decisions.",
            "Create clear technical direction.",
        ]
        assert all(
            chunk.document_type == DocumentType.ONE_TO_ONE
            for chunk in chunks
        )

    finally:
        if document_id:
            session.execute(
                delete(DocumentChunkDB).where(
                    DocumentChunkDB.document_id == document_id
                )
            )
            session.execute(
                delete(DocumentDB).where(DocumentDB.id == document_id)
            )

        if user_id:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )

        session.commit()
        session.close()
