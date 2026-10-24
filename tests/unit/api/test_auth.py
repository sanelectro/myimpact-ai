from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Annotated

import jwt
from app import auth
from app.auth import AuthenticatedUser, authorize_request_user, get_current_user
from app.main import app as main_app
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient


def _test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/users/{user_id}")
    def get_user(
        user_id: str,
        _: Annotated[AuthenticatedUser, Depends(authorize_request_user)],
    ) -> dict[str, str]:
        return {"user_id": user_id}

    @app.post("/items")
    def create_item(
        _: Annotated[AuthenticatedUser, Depends(authorize_request_user)],
    ) -> dict[str, str]:
        return {"created": "true"}

    @app.get("/api/v1/goals")
    def list_goals(
        _: Annotated[AuthenticatedUser, Depends(authorize_request_user)],
    ) -> dict[str, str]:
        return {"listed": "true"}

    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "user-1",
        "user-1@example.test",
        None,
        {"myimpact-ai"},
    )
    return app


def test_request_authorization_allows_matching_user_id():
    response = TestClient(_test_app()).get("/users/user-1?user_id=user-1")

    assert response.status_code == 200


def test_request_authorization_rejects_another_users_path_and_query():
    client = TestClient(_test_app())

    path_response = client.get("/users/user-2?user_id=user-1")
    query_response = client.get("/users/user-1?user_id=user-2")

    assert path_response.status_code == 403
    assert query_response.status_code == 403


def test_request_authorization_rejects_another_users_json_body():
    response = TestClient(_test_app()).post(
        "/items",
        json={"user_id": "user-2"},
    )

    assert response.status_code == 403


def test_request_authorization_rejects_another_users_form_body():
    response = TestClient(_test_app()).post(
        "/items",
        data={"user_id": "user-2"},
    )

    assert response.status_code == 403


def test_platform_admin_can_read_another_users_goal_data():
    app = _test_app()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "admin-1",
        "admin@example.test",
        None,
        {"myimpact-ai"},
        is_platform_admin=True,
    )
    response = TestClient(app).get("/api/v1/goals?user_id=employee-1")

    assert response.status_code == 200


def test_platform_admin_cannot_mutate_another_users_goal_data():
    app = _test_app()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "admin-1",
        "admin@example.test",
        None,
        {"myimpact-ai"},
        is_platform_admin=True,
    )
    response = TestClient(app).post("/items", json={"user_id": "employee-1"})

    assert response.status_code == 403


def test_current_user_validates_signature_issuer_audience_and_scope(monkeypatch):
    private_key = generate_private_key(public_exponent=65537, key_size=2048)
    settings = SimpleNamespace(
        auth_issuer="https://auth.example.test",
        auth_audience="myimpact-platform",
    )

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, _token: str) -> SimpleNamespace:
            return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "_get_jwks_client", lambda: FakeJwksClient())
    token = jwt.encode(
        {
            "sub": "user-1",
            "email": "user-1@example.com",
            "is_platform_admin": True,
            "scope": "myimpact-api myimpact-ai",
            "iss": settings.auth_issuer,
            "aud": settings.auth_audience,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
    )

    user = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))

    assert user.user_id == "user-1"
    assert user.email == "user-1@example.com"
    assert "myimpact-ai" in user.scopes
    assert user.is_platform_admin


def test_main_app_keeps_health_public_and_requires_auth_for_product_routes():
    main_app.dependency_overrides.pop(authorize_request_user, None)
    client = TestClient(main_app)

    assert client.get("/health").status_code == 200
    protected = client.post(
        "/api/v1/chat?user_id=user-1",
        json={"message": "Hello"},
    )
    assert protected.status_code == 401
