from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser, get_current_user
from app.db.base import Base
from app.db.models.organization import OrganizationDB
from app.db.models.user import UserDB
from app.db.models.user_invitation import UserInvitationDB
from app.db.session import get_db
from app.main import app

client = TestClient(app)


def _user(user_id: str, email: str, organization_id: str | None) -> UserDB:
    now = datetime.now(UTC)
    return UserDB(
        id=user_id,
        name=user_id.replace("-", " ").title(),
        email=email,
        role="Software Engineer",
        organization_id=organization_id,
        created_at=now,
        updated_at=now,
    )


def test_platform_admin_can_list_users_across_companies():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime.now(UTC)

    with test_session() as db:
        db.add_all(
            [
                OrganizationDB(
                    id="company-1",
                    name="Acme",
                    normalized_name="acme",
                    created_at=now,
                ),
                OrganizationDB(
                    id="company-2",
                    name="Globex",
                    normalized_name="globex",
                    created_at=now,
                ),
            ]
        )
        pending_user = _user("user-invite", "invite@example.com", "company-2")
        pending_user.is_active = False
        platform_admin = _user("platform-admin", "admin@myimpact.example", None)
        platform_admin.is_platform_admin = True
        db.add_all(
            [
                _user("user-acme", "acme@example.com", "company-1"),
                _user("user-globex", "globex@example.com", "company-2"),
                _user("user-unassigned", "user-empty@myimpact.local", None),
                pending_user,
                platform_admin,
                UserInvitationDB(
                    id="invite-1",
                    user_id="user-invite",
                    token_hash="hashed-invitation-token",
                    created_at=now,
                    expires_at=now,
                ),
            ]
        )
        db.commit()

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "admin-1",
        "admin@example.com",
        None,
        {"myimpact-ai"},
        is_platform_admin=True,
    )
    try:
        response = client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert response.status_code == 200
    users = response.json()
    assert {user["email"] for user in users} == {
        "acme@example.com",
        "globex@example.com",
        "user-empty@myimpact.local",
        "invite@example.com",
    }
    assert "admin@myimpact.example" not in {user["email"] for user in users}
    assert {user["company"] for user in users} == {"Acme", "Globex", None}
    invitation_users = {
        user["email"]: user["invitation_pending"] for user in users
    }
    assert invitation_users["invite@example.com"] is True
    assert invitation_users["acme@example.com"] is False


def test_non_admin_cannot_list_users_across_companies():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "user-1",
        "user-1@example.com",
        "Software Engineer",
        {"myimpact-ai"},
    )
    try:
        response = client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Platform administrator access is required."
    )


def test_platform_admin_can_list_and_update_companies():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    now = datetime.now(UTC)

    with test_session() as db:
        db.add_all(
            [
                OrganizationDB(
                    id="company-1",
                    name="Acme",
                    normalized_name="acme",
                    created_at=now,
                ),
                OrganizationDB(
                    id="company-2",
                    name="Globex",
                    normalized_name="globex",
                    created_at=now,
                ),
                _user("company-user", "employee@example.com", "company-1"),
            ]
        )
        db.commit()

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "admin-1",
        "admin@example.com",
        None,
        {"myimpact-ai"},
        is_platform_admin=True,
    )
    try:
        companies_response = client.get("/api/v1/admin/companies")
        update_response = client.patch(
            "/api/v1/admin/companies/company-1",
            json={"name": "  Acme   Global  "},
        )
        duplicate_response = client.patch(
            "/api/v1/admin/companies/company-1",
            json={"name": "Globex"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(engine)
        engine.dispose()

    assert companies_response.status_code == 200
    assert {
        company["name"]: company["user_count"]
        for company in companies_response.json()
    } == {"Acme": 1, "Globex": 0}
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Acme Global"
    assert update_response.json()["user_count"] == 1
    assert duplicate_response.status_code == 409


def test_non_admin_cannot_update_company():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "user-1",
        "user-1@example.com",
        "Software Engineer",
        {"myimpact-ai"},
    )
    try:
        response = client.patch(
            "/api/v1/admin/companies/company-1",
            json={"name": "Renamed"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        engine.dispose()

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Platform administrator access is required."
    )
