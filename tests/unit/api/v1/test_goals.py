from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.goals import get_goal_service
from app.db.models.goal import GoalDB
from app.main import app
from app.models.goal import GoalStatus
from app.services.goal import GoalService

client = TestClient(app)


def _goal(user_id="user-1"):
    now = datetime.now(UTC)
    return GoalDB(
        id="goal-1", user_id=user_id, title="Improve reliability",
        status=GoalStatus.ACTIVE, created_at=now, updated_at=now,
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
