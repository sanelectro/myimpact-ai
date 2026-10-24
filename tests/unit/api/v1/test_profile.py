from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.organization import OrganizationDB
from app.db.models.team import TeamDB
from app.db.models.user import UserDB
from app.db.session import get_db
from app.main import app


def test_profile_directory_and_team_scoped_manager_validation():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    OrganizationDB.__table__.create(engine)
    TeamDB.__table__.create(engine)
    UserDB.__table__.create(engine)
    session_factory = sessionmaker(bind=engine, class_=Session)
    db = session_factory()
    now = datetime.now(UTC)
    acme = OrganizationDB(
        id="org-acme",
        name="Acme",
        normalized_name="acme",
        created_at=now,
    )
    other_company = OrganizationDB(
        id="org-other",
        name="Other Co",
        normalized_name="other co",
        created_at=now,
    )
    engineering_team = TeamDB(
        id="team-engineering",
        organization_id=acme.id,
        name="Engineering",
        normalized_name="engineering",
        created_at=now,
    )
    product_team = TeamDB(
        id="team-product",
        organization_id=acme.id,
        name="Product",
        normalized_name="product",
        created_at=now,
    )
    engineer = UserDB(
        id="engineer",
        name="Engineer User",
        email="engineer@example.test",
        role=None,
        organization_id=None,
        reporting_manager_id=None,
        created_at=now,
        updated_at=now,
    )
    manager = UserDB(
        id="manager",
        name="Manager User",
        email="manager@example.test",
        role="Engineering Manager",
        organization_id=acme.id,
        team_id=engineering_team.id,
        reporting_manager_id=None,
        created_at=now,
        updated_at=now,
    )
    wrong_company_manager = UserDB(
        id="wrong-manager",
        name="Wrong Company Manager",
        email="wrong-manager@example.test",
        role="Engineering Manager",
        organization_id=other_company.id,
        reporting_manager_id=None,
        created_at=now,
        updated_at=now,
    )
    product_manager = UserDB(
        id="product-manager",
        name="Product Manager",
        email="product-manager@example.test",
        role="Engineering Manager",
        organization_id=acme.id,
        team_id=product_team.id,
        reporting_manager_id=None,
        created_at=now,
        updated_at=now,
    )
    db.add_all([
        acme,
        other_company,
        engineering_team,
        product_team,
        engineer,
        manager,
        wrong_company_manager,
        product_manager,
    ])
    db.commit()

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        engineer.id,
        engineer.email,
        engineer.role,
        {"myimpact-ai"},
        engineer.name,
    )
    client = TestClient(app)
    try:
        options = client.get(
            "/api/v1/profile/reporting-managers",
            params={
                "company": "ACME",
                "role": "Software Engineer",
                "team": "Engineering",
            },
        )
        assert options.status_code == 200
        assert options.json() == []

        wrong_company_options = client.get(
            "/api/v1/profile/reporting-managers",
            params={"company": "Other Co", "role": "Software Engineer"},
        )
        assert wrong_company_options.status_code == 200
        assert wrong_company_options.json() == []

        saved = client.put(
            "/api/v1/profile",
            json={
                "company": " acme ",
                "team": " Engineering ",
                "role": None,
                "reporting_manager_id": manager.id,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["company"] == "Acme"
        assert saved.json()["team"] == "Engineering"
        assert saved.json()["reporting_manager"]["id"] == manager.id
        assert saved.json()["direct_reports"] == []

        created_team = client.put(
            "/api/v1/profile",
            json={
                "company": "Acme",
                "team": "Platform",
                "role": None,
                "reporting_manager_id": None,
            },
        )
        assert created_team.status_code == 200
        assert created_team.json()["team"] == "Platform"

        teams = client.get(
            "/api/v1/profile/teams",
            params={"company": "Acme"},
        )
        assert teams.status_code == 200
        assert [team["name"] for team in teams.json()] == [
            "Engineering",
            "Platform",
            "Product",
        ]

        options = client.get(
            "/api/v1/profile/reporting-managers",
            params={
                "company": "ACME",
                "role": "Software Engineer",
                "team": "Engineering",
            },
        )
        assert options.status_code == 200
        assert [manager["id"] for manager in options.json()] == ["manager"]

        team_options = client.get(
            "/api/v1/profile/reporting-managers",
            params={
                "company": "Acme",
                "role": "Software Engineer",
                "team": "Product",
            },
        )
        assert team_options.status_code == 200
        assert [manager["id"] for manager in team_options.json()] == ["product-manager"]

        organization_options = client.get(
            "/api/v1/profile/reporting-managers",
            params={"company": "Acme", "role": "Software Engineer"},
        )
        assert [manager["id"] for manager in organization_options.json()] == [
            "manager",
            "product-manager",
        ]

        rejected = client.put(
            "/api/v1/profile",
            json={
                "company": "Acme",
                "role": None,
                "reporting_manager_id": wrong_company_manager.id,
            },
        )
        assert rejected.status_code == 422
        assert "same company" in rejected.json()["error"]["message"]

        rejected_team = client.put(
            "/api/v1/profile",
            json={
                "company": "Acme",
                "team": "Product",
                "role": None,
                "reporting_manager_id": manager.id,
            },
        )
        assert rejected_team.status_code == 422
        assert "same team" in rejected_team.json()["error"]["message"]

        rejected_hierarchy = client.put(
            "/api/v1/profile",
            json={
                "company": "Acme",
                "role": "Engineering Manager",
                "reporting_manager_id": manager.id,
            },
        )
        assert rejected_hierarchy.status_code == 403
        assert "reporting manager" in rejected_hierarchy.json()["error"]["message"]

        restored_reporting_line = client.put(
            "/api/v1/profile",
            json={
                "company": "Acme",
                "team": "Engineering",
                "role": None,
                "reporting_manager_id": manager.id,
            },
        )
        assert restored_reporting_line.status_code == 200

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            manager.id,
            manager.email,
            manager.role,
            {"myimpact-ai"},
            manager.name,
        )
        manager_profile = client.get("/api/v1/profile")
        assert manager_profile.status_code == 200
        assert [report["id"] for report in manager_profile.json()["direct_reports"]] == [
            engineer.id
        ]
        assert "Software Engineer" in manager_profile.json()["direct_report_role_options"]

        initial_role = client.patch(
            f"/api/v1/profile/direct-reports/{engineer.id}/role",
            json={"role": "Software Engineer"},
        )
        assert initial_role.status_code == 200
        assert initial_role.json()["role"] == "Software Engineer"

        updated_role = client.patch(
            f"/api/v1/profile/direct-reports/{engineer.id}/role",
            json={"role": "Senior Software Engineer"},
        )
        assert updated_role.status_code == 200
        assert updated_role.json()["role"] == "Senior Software Engineer"

        rejected_role = client.patch(
            f"/api/v1/profile/direct-reports/{engineer.id}/role",
            json={"role": "Engineering Manager"},
        )
        assert rejected_role.status_code == 422

        rejected_non_report = client.patch(
            f"/api/v1/profile/direct-reports/{product_manager.id}/role",
            json={"role": "Senior Software Engineer"},
        )
        assert rejected_non_report.status_code == 404

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            engineer.id,
            engineer.email,
            engineer.role,
            {"myimpact-ai"},
            engineer.name,
        )
        self_role_change = client.put(
            "/api/v1/profile",
            json={
                "company": "Acme",
                "team": "Engineering",
                "role": "Software Engineer",
                "reporting_manager_id": manager.id,
            },
        )
        assert self_role_change.status_code == 403
        assert "reporting manager" in self_role_change.json()["error"]["message"]
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        db.close()
        engine.dispose()
