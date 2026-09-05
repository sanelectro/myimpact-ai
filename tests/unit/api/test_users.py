from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.users import get_user_service
from app.db.models.user import UserDB
from app.main import app
from app.services.user import UserService

client = TestClient(app)

def test_create_user():
    service = MagicMock(spec=UserService)

    expected_user = UserDB(
        id="user-123",
        name="Test User",
        email="test@example.com",
        role="Engineer",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    service.create_user.return_value = expected_user

    def override_get_user_service():
        return service

    app.dependency_overrides[get_user_service] = override_get_user_service

    try:
        response = client.post(
            "/users",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "role": "Engineer",
            },
        )

        assert response.status_code == 201

        data = response.json()

        assert data["id"] == "user-123"
        assert data["name"] == "Test User"
        assert data["email"] == "test@example.com"
        assert data["role"] == "Engineer"

        service.create_user.assert_called_once()
    finally:
        app.dependency_overrides.clear()
        
        
        
def test_get_user_by_id():
    service = MagicMock(spec=UserService)

    expected_user = UserDB(
        id="user-123",
        name="Test User",
        email="test@example.com",
        role="Engineer",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    service.get_user_by_id.return_value = expected_user

    def override_get_user_service():
        return service

    app.dependency_overrides[get_user_service] = override_get_user_service

    try:
        response = client.get("/users/user-123")

        assert response.status_code == 200

        data = response.json()

        assert data["id"] == "user-123"
        assert data["name"] == "Test User"
        assert data["email"] == "test@example.com"

        service.get_user_by_id.assert_called_once_with("user-123")
    finally:
        app.dependency_overrides.clear()
        
        
def test_get_user_by_id_returns_404():
    service = MagicMock(spec=UserService)
    service.get_user_by_id.return_value = None

    def override_get_user_service():
        return service

    app.dependency_overrides[get_user_service] = override_get_user_service

    try:
        response = client.get("/users/missing-user")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

        service.get_user_by_id.assert_called_once_with("missing-user")
    finally:
        app.dependency_overrides.clear()
        
        
        
        
def test_get_user_by_email():
    service = MagicMock(spec=UserService)

    expected_user = UserDB(
        id="user-123",
        name="Test User",
        email="test@example.com",
        role="Engineer",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    service.get_user_by_email.return_value = expected_user

    def override_get_user_service():
        return service

    app.dependency_overrides[get_user_service] = override_get_user_service

    try:
        response = client.get("/users/email/test@example.com")

        assert response.status_code == 200

        data = response.json()

        assert data["id"] == "user-123"
        assert data["email"] == "test@example.com"

        service.get_user_by_email.assert_called_once_with(
            "test@example.com"
        )
    finally:
        app.dependency_overrides.clear()
        
        
def test_get_user_by_email_returns_404():
    service = MagicMock(spec=UserService)
    service.get_user_by_email.return_value = None

    def override_get_user_service():
        return service

    app.dependency_overrides[get_user_service] = override_get_user_service

    try:
        response = client.get("/users/email/missing@example.com")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

        service.get_user_by_email.assert_called_once_with(
            "missing@example.com"
        )
    finally:
        app.dependency_overrides.clear()