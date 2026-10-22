from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.document import DocumentDB
from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.document import DocumentStatus, DocumentType
from app.models.goal import GoalScope, GoalStatus
from app.models.goal_import import GoalImportCandidate, GoalImportExtractionResult
from app.models.user import UserCreate
from app.repositories.document import DocumentRepository
from app.services.goal import GoalService
from app.services.goal_import import GoalImportService
from app.services.user import UserService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_goal_import_persists_drafts_is_idempotent_and_skips_cross_document_duplicates():
    session = SessionLocal()
    user_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M6.3 Goal Import User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        document_repository = DocumentRepository(session)
        documents = []
        for file_name, content_type in (
            ("goals.pdf", "application/pdf"),
            (
                "goals.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ):
            document_id = str(uuid4())
            document = document_repository.create(
                document_id=document_id,
                user_id=user_id,
                document_type=DocumentType.GOAL,
                file_name=file_name,
                content_type=content_type,
                storage_path=f"documents/{user_id}/{file_name}",
            )
            document_repository.update_processing(
                document_id=document_id,
                extracted_content_path=f"documents/{user_id}/{document_id}.md",
                status=DocumentStatus.PROCESSED,
            )
            documents.append(document)
        session.commit()

        storage = MagicMock()
        storage.read.return_value = b"Extracted goal content"
        service = GoalImportService(session, storage, MagicMock())
        extracted_goals = GoalImportExtractionResult(
            goals=[
                GoalImportCandidate(
                    title="Improve deployment reliability",
                    description="Reduce deployment-related incidents",
                    scope=GoalScope.TEAM,
                    confidence=0.95,
                )
            ]
        )
        service._extract = AsyncMock(
            side_effect=[extracted_goals, extracted_goals]
        )

        first_import = await service.import_from_document(documents[0].id, user_id)
        assert len(first_import["imported_goals"]) == 1
        imported_goal = first_import["imported_goals"][0]
        assert imported_goal.status == GoalStatus.DRAFT
        assert imported_goal.source_document_id == documents[0].id

        repeated_import = await service.import_from_document(documents[0].id, user_id)
        assert [goal.id for goal in repeated_import["imported_goals"]] == [imported_goal.id]
        assert repeated_import["skipped_duplicates"] == []
        assert service._extract.await_count == 1

        cross_document_import = await service.import_from_document(documents[1].id, user_id)
        assert cross_document_import["imported_goals"] == []
        assert cross_document_import["skipped_duplicates"] == [
            {
                "title": "Improve deployment reliability",
                "existing_goal_id": imported_goal.id,
            }
        ]
        assert service._extract.await_count == 2
        persisted_goals = GoalService(session).get_goals_by_user_id(user_id)
        assert [goal.id for goal in persisted_goals] == [imported_goal.id]
    finally:
        if user_id is not None:
            session.execute(delete(GoalDB).where(GoalDB.user_id == user_id))
            session.execute(delete(DocumentDB).where(DocumentDB.user_id == user_id))
            session.execute(delete(UserDB).where(UserDB.id == user_id))
            session.commit()
        session.close()
