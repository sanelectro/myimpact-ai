from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app import auth
from app.auth import authorize_request_user
from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.goal import GoalCreate
from app.models.user import UserCreate
from app.services.goal import GoalService
from app.services.user import UserService

AUTH_ISSUER = "https://auth.example.test"
AUTH_AUDIENCE = "myimpact-platform"


@pytest.mark.integration
def test_authenticated_goal_access_enforces_user_isolation(monkeypatch):
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    settings = SimpleNamespace(
        auth_issuer=AUTH_ISSUER,
        auth_audience=AUTH_AUDIENCE,
    )

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token: str) -> SimpleNamespace:
            return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "_get_jwks_client", lambda: FakeJwksClient())
    app.dependency_overrides.pop(authorize_request_user, None)

    session = SessionLocal()
    user_ids: list[str] = []
    client = TestClient(app)

    def access_token(user_id: str, email: str) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": user_id,
                "email": email,
                "scope": "myimpact-api myimpact-ai",
                "iss": AUTH_ISSUER,
                "aud": AUTH_AUDIENCE,
                "iat": now,
                "exp": now + timedelta(minutes=5),
            },
            private_key,
            algorithm="RS256",
        )

    try:
        user_service = UserService(session)
        user_a = user_service.create_user(
            UserCreate(name="Authorization User A", email=f"{uuid4()}@example.com")
        )
        user_b = user_service.create_user(
            UserCreate(name="Authorization User B", email=f"{uuid4()}@example.com")
        )
        user_ids.extend((user_a.id, user_b.id))
        goal_service = GoalService(session)
        goal_a = goal_service.create_goal(
            GoalCreate(user_id=user_a.id, title="User A goal")
        )
        goal_b = goal_service.create_goal(
            GoalCreate(user_id=user_b.id, title="User B goal")
        )

        unauthorized = client.get(
            "/api/v1/goals",
            params={"user_id": user_a.id},
        )
        assert unauthorized.status_code == 401

        headers = {
            "Authorization": f"Bearer {access_token(user_a.id, user_a.email)}"
        }
        own_goals = client.get(
            "/api/v1/goals",
            params={"user_id": user_a.id},
            headers=headers,
        )
        assert own_goals.status_code == 200
        assert [goal["id"] for goal in own_goals.json()] == [goal_a.id]

        other_user_query = client.get(
            "/api/v1/goals",
            params={"user_id": user_b.id},
            headers=headers,
        )
        assert other_user_query.status_code == 403

        other_user_goal = client.get(
            f"/api/v1/goals/{goal_b.id}",
            params={"user_id": user_a.id},
            headers=headers,
        )
        assert other_user_goal.status_code == 404
    finally:
        client.close()
        if user_ids:
            session.execute(delete(GoalDB).where(GoalDB.user_id.in_(user_ids)))
            session.execute(delete(UserDB).where(UserDB.id.in_(user_ids)))
            session.commit()
        session.close()
