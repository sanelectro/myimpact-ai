from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.goals import get_goal_service
from app.db.models.goal import GoalDB
from app.main import app
from app.models.goal import GoalStatus
from app.services.goal import GoalService

client = TestClient(app)


def _goal():
    now = datetime.now(UTC)
    return GoalDB(
        id="goal-1", user_id="user-1", title="Improve reliability",
        status=GoalStatus.ACTIVE, created_at=now, updated_at=now,
    )


def test_create_goal():
    service = MagicMock(spec=GoalService)
    service.create_goal.return_value = _goal()
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.post("/goals", json={"user_id": "user-1", "title": "Improve reliability"})
        assert response.status_code == 201
        assert response.json()["id"] == "goal-1"
        service.create_goal.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_get_goal_by_id():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = _goal()
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.get("/goals/goal-1")
        assert response.status_code == 200
        assert response.json()["id"] == "goal-1"
    finally:
        app.dependency_overrides.clear()


def test_get_goal_by_id_returns_404():
    service = MagicMock(spec=GoalService)
    service.get_goal_by_id.return_value = None
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.get("/goals/missing")
        assert response.status_code == 404
        assert response.json()["detail"] == "Goal not found"
    finally:
        app.dependency_overrides.clear()


def test_get_goals_by_user_id():
    service = MagicMock(spec=GoalService)
    service.get_goals_by_user_id.return_value = [_goal()]
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        response = client.get("/goals/user/user-1")
        assert response.status_code == 200
        assert len(response.json()) == 1
    finally:
        app.dependency_overrides.clear()
