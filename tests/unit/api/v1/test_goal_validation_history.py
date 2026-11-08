from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.v1.goals import get_goal_service, get_goal_validation_service
from app.db.models.goal import GoalDB
from app.main import app
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.services.goal import GoalService
from app.services.goal_validation import GoalSemanticValidationError
from app.services.goal_validation_runs import GoalValidationRunService

client = TestClient(app)


def _goal(user_id: str) -> GoalDB:
    now = datetime.now(UTC)
    return GoalDB(
        id="goal-1",
        user_id=user_id,
        title="Goal",
        scope=GoalScope.PERSONAL,
        status=GoalStatus.DRAFT,
        sub_status=GoalSubStatus.NEEDS_REVIEW,
        created_at=now,
        updated_at=now,
    )


def test_non_owner_cannot_validate_or_read_validation_history():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal("owner-1")
    validation_service = MagicMock(spec=GoalValidationRunService)
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    app.dependency_overrides[get_goal_validation_service] = lambda: validation_service
    try:
        validate_response = client.post(
            "/api/v1/goals/goal-1/validate",
            params={"user_id": "other-user"},
        )
        history_response = client.get(
            "/api/v1/goals/goal-1/validation-history",
            params={"user_id": "other-user"},
        )
    finally:
        app.dependency_overrides.clear()

    assert validate_response.status_code == 404
    assert history_response.status_code == 404
    validation_service.validate_latest.assert_not_called()
    validation_service.get_history.assert_not_called()


def test_validation_provider_failure_is_not_returned_as_ready():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal("owner-1")
    validation_service = MagicMock(spec=GoalValidationRunService)
    validation_service.validate_latest = AsyncMock(
        side_effect=GoalSemanticValidationError("Semantic validation failed.")
    )
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    app.dependency_overrides[get_goal_validation_service] = lambda: validation_service
    try:
        response = client.post(
            "/api/v1/goals/goal-1/validate",
            params={"user_id": "owner-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Semantic validation failed."
    assert "READY" not in response.text
    validation_service.validate_latest.assert_awaited_once_with("goal-1", "owner-1")


def test_validation_response_identifies_version_and_records_metadata():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal("owner-1")
    run = SimpleNamespace(
        id="run-1",
        goal_id="goal-1",
        goal_version_id="version-2",
        goal_version=SimpleNamespace(version=2),
        status="READY",
        findings=[],
        rule_set_version="goal-rules-v1",
        prompt_version="goal-semantic-validation-v1",
        model_provider="test-provider",
        model_version="test-model",
        actor_user_id="owner-1",
        created_at=datetime.now(UTC),
    )
    validation_service = MagicMock(spec=GoalValidationRunService)
    validation_service.validate_latest = AsyncMock(return_value=run)
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    app.dependency_overrides[get_goal_validation_service] = lambda: validation_service
    try:
        response = client.post(
            "/api/v1/goals/goal-1/validate",
            params={"user_id": "owner-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["goal_version_id"] == "version-2"
    assert response.json()["goal_version"] == 2
    assert response.json()["model_provider"] == "test-provider"
    assert response.json()["actor_user_id"] == "owner-1"
