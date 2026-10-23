from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models.goal import GoalDB
from app.db.models.goal_status_history import GoalStatusHistoryDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserCreate
from app.services.user import UserService

client = TestClient(app)


@pytest.mark.integration
def test_goal_api_crud_assessment_isolation_and_full_lifecycle():
    session = SessionLocal()
    user_id = None
    goal_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="M6.3 Lifecycle API User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        created = client.post(
            "/api/v1/goals",
            params={"user_id": user_id},
            json={"title": "Improve deployment reliability", "scope": "team"},
        )
        assert created.status_code == 201
        goal = created.json()
        goal_id = goal["id"]
        assert goal["status"] == "draft"
        assert goal["sub_status"] == "needs_review"
        assert goal["scope"] == "team"

        listed = client.get("/api/v1/goals", params={"user_id": user_id})
        assert listed.status_code == 200
        assert any(item["id"] == goal_id for item in listed.json())

        viewed = client.get(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": user_id},
        )
        assert viewed.status_code == 200
        assert viewed.json()["title"] == "Improve deployment reliability"

        updated = client.put(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": f"not-{user_id}"},
            json={"title": "Unauthorized change"},
        )
        assert updated.status_code == 404

        updated = client.put(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": user_id},
            json={"title": "Improve deployment reliability by 30%", "scope": "organization"},
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Improve deployment reliability by 30%"
        assert updated.json()["scope"] == "organization"

        assessment = client.get(
            f"/api/v1/goals/{goal_id}/assessment",
            params={"user_id": user_id},
        )
        assert assessment.status_code == 200
        assert assessment.json()["status"] == "not_started"
        assert assessment.json()["qualifying_achievement_count"] == 0

        wrong_owner = client.get(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": f"not-{user_id}"},
        )
        assert wrong_owner.status_code == 404

        invalid_transition = client.post(
            f"/api/v1/goals/{goal_id}/complete",
            params={"user_id": user_id},
        )
        assert invalid_transition.status_code == 422

        transitions = (
            ("approve", "approved", "not_started"),
            ("activate", "active", "on_track"),
            ("complete", "completed", "completed"),
        )
        for action, expected_status, expected_sub_status in transitions:
            response = client.post(
                f"/api/v1/goals/{goal_id}/{action}",
                params={"user_id": user_id},
            )
            assert response.status_code == 200
            assert response.json()["status"] == expected_status
            assert response.json()["sub_status"] == expected_sub_status

        archived = client.post(
            f"/api/v1/goals/{goal_id}/deactivate",
            params={"user_id": user_id},
            json={"reason": "Goal cycle complete"},
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"
        assert archived.json()["sub_status"] == "none"
        assert archived.json()["deactivation_reason"] == "Goal cycle complete"

        history = client.get(
            f"/api/v1/goals/{goal_id}/history",
            params={"user_id": user_id},
        )
        assert history.status_code == 200
        assert [entry["to_status"] for entry in history.json()] == [
            "archived",
            "completed",
            "active",
            "approved",
        ]
    finally:
        if goal_id is not None:
            session.execute(
                delete(GoalStatusHistoryDB).where(
                    GoalStatusHistoryDB.goal_id == goal_id
                )
            )
            session.execute(delete(GoalDB).where(GoalDB.id == goal_id))
        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()
