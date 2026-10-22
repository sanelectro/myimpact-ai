from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.goals import get_goal_service
from app.db.models.goal import GoalDB
from app.main import app
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.services.goal import GoalService

client = TestClient(app)


def _goal(user_id="user-1", status=GoalStatus.ACTIVE, deactivation_reason=None):
    now = datetime.now(UTC)
    return GoalDB(
        id="goal-1", user_id=user_id, title="Improve reliability",
        scope=GoalScope.PERSONAL, status=status, sub_status=GoalSubStatus.ON_TRACK,
        deactivation_reason=deactivation_reason, created_at=now, updated_at=now,
    )


def test_goal_routes_are_mounted():
    service = MagicMock(spec=GoalService)
    service.get_goals_by_user_id.return_value = []
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.get("/api/v1/goals", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200


def test_create_goal_returns_product_safe_contract():
    service = MagicMock(spec=GoalService)
    service.create_goal.return_value = _goal()
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.post("/api/v1/goals", params={"user_id": "user-1"}, json={"title": "Improve reliability"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    assert response.json()["id"] == "goal-1"
    assert "user_id" not in response.json()


def test_get_goal_enforces_user_isolation():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal(user_id="owner")
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.get("/api/v1/goals/goal-1", params={"user_id": "other-user"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_deactivate_goal_persists_and_returns_reason():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal()
    service.transition_status.return_value = _goal(
        status=GoalStatus.ARCHIVED,
        deactivation_reason="Priorities changed",
    )
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/goals/goal-1/deactivate",
            params={"user_id": "user-1"},
            json={"reason": "Priorities changed"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert response.json()["deactivation_reason"] == "Priorities changed"
    service.transition_status.assert_called_once_with(
        "goal-1",
        GoalStatus.ARCHIVED,
        reason="Priorities changed",
        changed_by_user_id="user-1",
    )


def test_deactivate_goal_rejects_blank_reason():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal()
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/goals/goal-1/deactivate",
            params={"user_id": "user-1"},
            json={"reason": "   "},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    service.transition_status.assert_not_called()


def test_reopen_goal_requires_and_records_reason():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal(status=GoalStatus.COMPLETED)
    service.transition_status.return_value = _goal(status=GoalStatus.ACTIVE)
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/goals/goal-1/reopen",
            params={"user_id": "user-1"},
            json={"reason": "The outcome requires another iteration"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    service.transition_status.assert_called_once_with(
        "goal-1",
        GoalStatus.ACTIVE,
        reason="The outcome requires another iteration",
        changed_by_user_id="user-1",
    )


def test_reopen_goal_rejects_blank_reason():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal(status=GoalStatus.COMPLETED)
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/goals/goal-1/reopen",
            params={"user_id": "user-1"},
            json={"reason": "   "},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    service.transition_status.assert_not_called()


def test_goal_status_history_is_returned_for_owner():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal()
    service.get_status_history.return_value = []
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.get(
            "/api/v1/goals/goal-1/history",
            params={"user_id": "user-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []
    service.get_status_history.assert_called_once_with("goal-1")


def test_delete_goal_requires_archived_status():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal(status=GoalStatus.ACTIVE)
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.delete(
            "/api/v1/goals/goal-1",
            params={"user_id": "user-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    service.delete_goal.assert_not_called()
