from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserCreate
from app.services.user import UserService

client = TestClient(app)


@pytest.mark.integration
def test_goal_api_create_and_get():
    session = SessionLocal()
    user_id = None
    goal_id = None
    try:
        user = UserService(session).create_user(UserCreate(name="Goal API User", email=f"{uuid4()}@example.com"))
        user_id = user.id
        response = client.post("/goals", json={"user_id": user_id, "title": "Improve reliability"})
        assert response.status_code == 201
        goal_id = response.json()["id"]
        response = client.get(f"/goals/{goal_id}")
        assert response.status_code == 200
        assert response.json()["user_id"] == user_id
    finally:
        if goal_id:
            session.execute(delete(GoalDB).where(GoalDB.id == goal_id))
        if user_id:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()


@pytest.mark.integration
def test_goal_api_missing_returns_404():
    assert client.get("/goals/missing-goal").status_code == 404
