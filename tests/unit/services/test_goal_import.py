from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.exceptions import LLMQuotaExceededError
from app.db.models.document import DocumentDB
from app.models.goal import GoalScope, GoalStatus
from app.models.goal_import import GoalImportExtractionResult, GoalImportCandidate
from app.models.llm import LLMResponse
from app.services.goal_import import (
    GOAL_EXTRACTION_MAX_RETRIES,
    GOAL_EXTRACTION_RETRY_DELAY_SECONDS,
    GoalImportService,
)


@pytest.mark.asyncio
async def test_import_from_document_creates_draft_goals():
    session = MagicMock(spec=Session)
    storage = MagicMock()
    llm = MagicMock()
    llm.generate = AsyncMock()

    document = DocumentDB(
        id="doc-1", user_id="user-1", extracted_content_path="doc/extracted.md",
        file_name="goals.pdf", content_type="application/pdf", storage_path="doc/goals.pdf",
    )
    service = GoalImportService(session, storage, llm)
    service.document_repository.get_by_id = MagicMock(return_value=document)
    service.goal_service.repository.get_by_source_document_id = MagicMock(return_value=[])
    service.goal_service.get_goals_by_user_id = MagicMock(return_value=[])
    service._extract = AsyncMock(return_value=GoalImportExtractionResult(goals=[
        GoalImportCandidate(title="Improve reliability", scope=GoalScope.TEAM, confidence=0.95)
    ]))
    service.goal_service.create_goal = MagicMock(side_effect=lambda data: MagicMock(
        id="goal-1", user_id=data.user_id, title=data.title, status=data.status, scope=data.scope,
    ))

    result = await service.import_from_document("doc-1", "user-1")

    assert len(result["imported_goals"]) == 1
    assert result["imported_goals"][0].status == GoalStatus.DRAFT
    assert result["imported_goals"][0].scope == GoalScope.TEAM
    assert result["skipped_duplicates"] == []
    service.goal_service.create_goal.assert_called_once()
    assert service.goal_service.create_goal.call_args.args[0].source_document_id == "doc-1"


@pytest.mark.asyncio
async def test_import_from_document_is_idempotent():
    session = MagicMock(spec=Session)
    storage = MagicMock()
    llm = MagicMock()
    service = GoalImportService(session, storage, llm)
    document = MagicMock(user_id="user-1", extracted_content_path="doc/extracted.md")
    existing = [MagicMock(id="goal-1")]
    service.document_repository.get_by_id = MagicMock(return_value=document)
    service.goal_service.repository.get_by_source_document_id = MagicMock(return_value=existing)

    result = await service.import_from_document("doc-1", "user-1")

    assert result["imported_goals"] == existing
    assert result["skipped_duplicates"] == []


@pytest.mark.asyncio
async def test_import_rejects_document_owned_by_another_user():
    service = GoalImportService(MagicMock(spec=Session), MagicMock(), MagicMock())
    service.document_repository.get_by_id = MagicMock(
        return_value=MagicMock(
            user_id="document-owner",
            extracted_content_path="doc/extracted.md",
        )
    )

    with pytest.raises(ValueError, match="Document not found"):
        await service.import_from_document("doc-1", "different-user")

    service.storage.read.assert_not_called()


@pytest.mark.asyncio
async def test_goal_extraction_requests_json_response():
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=LLMResponse(content='{"goals":[]}'))
    service = GoalImportService(MagicMock(spec=Session), MagicMock(), llm)

    result = await service._extract("A document with no goals")

    assert result.goals == []
    request = llm.generate.await_args.args[0]
    assert request.response_format == {"type": "json_object"}


@pytest.mark.asyncio
async def test_goal_extraction_retries_invalid_output_then_succeeds():
    llm = MagicMock()
    llm.generate = AsyncMock(
        side_effect=[
            LLMResponse(content="not-json"),
            LLMResponse(content='{"goals":[]}'),
        ]
    )
    service = GoalImportService(MagicMock(spec=Session), MagicMock(), llm)

    with patch("app.services.goal_import.asyncio.sleep", new_callable=AsyncMock) as delay:
        result = await service._extract("A document with no goals")

    assert result.goals == []
    assert llm.generate.await_count == 2
    delay.assert_awaited_once_with(GOAL_EXTRACTION_RETRY_DELAY_SECONDS)


@pytest.mark.asyncio
async def test_goal_extraction_stops_after_five_retries():
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=LLMResponse(content="not-json")
    )
    service = GoalImportService(MagicMock(spec=Session), MagicMock(), llm)

    with patch("app.services.goal_import.asyncio.sleep", new_callable=AsyncMock) as delay:
        with pytest.raises(ValueError, match="invalid response"):
            await service._extract("A document with no goals")

    assert llm.generate.await_count == GOAL_EXTRACTION_MAX_RETRIES + 1 == 6
    assert delay.await_count == GOAL_EXTRACTION_MAX_RETRIES == 5


@pytest.mark.asyncio
async def test_goal_extraction_surfaces_quota_exhaustion_without_retrying():
    class QuotaError(Exception):
        code = "insufficient_quota"

    llm = MagicMock()
    llm.generate = AsyncMock(side_effect=QuotaError("quota exhausted"))
    service = GoalImportService(MagicMock(spec=Session), MagicMock(), llm)

    with patch("app.services.goal_import.asyncio.sleep", new_callable=AsyncMock) as delay:
        with pytest.raises(LLMQuotaExceededError, match="quota or token balance"):
            await service._extract("A document with goals")

    assert llm.generate.await_count == 1
    delay.assert_not_awaited()


def _goal(goal_id: str, title: str, description: str | None = None, scope: GoalScope = GoalScope.TEAM):
    return MagicMock(id=goal_id, title=title, description=description, scope=scope)


@pytest.mark.parametrize(
    ("candidate", "existing", "expected"),
    [
        ("Improve deployment reliability", "Improve deployment reliability", True),
        ("Improve deployment reliability across services", "Improve deployment reliability", True),
        ("Improve deployment reliability", "Improve customer satisfaction", False),
    ],
)
def test_duplicate_detection(candidate, existing, expected):
    result = GoalImportService._find_duplicate_goal(
        title=candidate,
        description=None,
        scope=GoalScope.TEAM,
        existing_goals=[_goal("goal-1", existing)],
    )
    assert (result is not None) is expected


def test_duplicate_detection_ignores_different_scope():
    result = GoalImportService._find_duplicate_goal(
        title="Improve deployment reliability",
        description=None,
        scope=GoalScope.PERSONAL,
        existing_goals=[_goal("goal-1", "Improve deployment reliability", scope=GoalScope.TEAM)],
    )
    assert result is None


@pytest.mark.asyncio
async def test_import_from_document_skips_existing_and_creates_new_goals():
    session = MagicMock(spec=Session)
    storage = MagicMock()
    llm = MagicMock()
    service = GoalImportService(session, storage, llm)
    document = DocumentDB(
        id="doc-2", user_id="user-1", extracted_content_path="doc/extracted.md",
        file_name="JL5-roles.docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        storage_path="doc/JL5-roles.docx",
    )
    service.document_repository.get_by_id = MagicMock(return_value=document)
    service.goal_service.repository.get_by_source_document_id = MagicMock(return_value=[])
    service.goal_service.get_goals_by_user_id = MagicMock(return_value=[
        _goal("existing-1", "Improve deployment reliability", "Reduce deployment-related incidents")
    ])
    service._extract = AsyncMock(return_value=GoalImportExtractionResult(goals=[
        GoalImportCandidate(title="Improve deployment reliability", description="Reduce deployment-related incidents", scope=GoalScope.TEAM),
        GoalImportCandidate(title="Improve architecture quality", description="Improve technical design quality", scope=GoalScope.TEAM),
    ]))
    service.goal_service.create_goal = MagicMock(side_effect=lambda data: MagicMock(
        id="new-1", title=data.title, status=data.status, scope=data.scope,
    ))

    result = await service.import_from_document("doc-2", "user-1")

    assert len(result["imported_goals"]) == 1
    assert result["imported_goals"][0].title == "Improve architecture quality"
    assert result["skipped_duplicates"] == [{"title": "Improve deployment reliability", "existing_goal_id": "existing-1"}]
    service.goal_service.create_goal.assert_called_once()
