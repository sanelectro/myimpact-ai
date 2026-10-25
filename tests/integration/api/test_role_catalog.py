from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.organization import OrganizationDB
from app.db.models.organization_role import (
    OrganizationRoleAuditEventDB,
    OrganizationRoleCompetencyDB,
    OrganizationRoleDB,
    OrganizationRoleGoalDB,
    OrganizationRoleResponsibilityDB,
)
from app.db.models.user import UserDB
from app.db.session import get_db
from app.main import app


def test_company_role_catalog_crud_history_and_authorization():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (OrganizationDB, UserDB):
        model.__table__.create(engine)
    for model in (
        OrganizationRoleDB,
        OrganizationRoleResponsibilityDB,
        OrganizationRoleGoalDB,
        OrganizationRoleCompetencyDB,
        OrganizationRoleAuditEventDB,
    ):
        model.__table__.create(engine)

    session_factory = sessionmaker(bind=engine, class_=Session)
    db = session_factory()
    now = datetime.now(UTC)
    northstar = OrganizationDB(
        id="org-northstar",
        name="Northstar",
        normalized_name="northstar",
        created_at=now,
    )
    other_company = OrganizationDB(
        id="org-other",
        name="Other Company",
        normalized_name="other company",
        created_at=now,
    )
    users = {
        "manager": UserDB(
            id="manager",
            name="Erin Manager",
            email="manager@example.test",
            role="Engineering Manager",
            organization_id=northstar.id,
            created_at=now,
            updated_at=now,
        ),
        "senior_manager": UserDB(
            id="senior-manager",
            name="Sam Senior Manager",
            email="senior-manager@example.test",
            role="Senior Engineering Manager",
            organization_id=northstar.id,
            created_at=now,
            updated_at=now,
        ),
        "director": UserDB(
            id="director",
            name="Drew Director",
            email="director@example.test",
            role="Engineering Director",
            organization_id=northstar.id,
            created_at=now,
            updated_at=now,
        ),
        "employee": UserDB(
            id="employee",
            name="Elliot Engineer",
            email="employee@example.test",
            role="Senior Software Engineer",
            organization_id=northstar.id,
            created_at=now,
            updated_at=now,
        ),
        "other_manager": UserDB(
            id="other-manager",
            name="Morgan Other",
            email="other-manager@example.test",
            role="Engineering Manager",
            organization_id=other_company.id,
            created_at=now,
            updated_at=now,
        ),
    }
    db.add_all([northstar, other_company, *users.values()])
    db.commit()

    current_user_id = {"value": "manager"}

    def override_db():
        yield db

    def override_user():
        user = users[current_user_id["value"]]
        return AuthenticatedUser(
            user.id,
            user.email,
            user.role,
            {"myimpact-ai"},
            user.name,
        )

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    try:
        payload = {
            "name": "Platform Reliability Lead",
            "summary": "Guides reliability work across the company.",
            "responsibilities": [
                {"statement": "Set reliability direction."},
                {"statement": "Coach service teams."},
            ],
            "goals": [
                {
                    "title": "Improve service resilience",
                    "description": "Establish a reviewed resilience plan.",
                }
            ],
            "competencies": [
                {
                    "name": "Incident management",
                    "expected_level": "Advanced",
                    "description": "Lead incident reviews.",
                }
            ],
        }
        created = client.post("/api/v1/role-catalog/roles", json=payload)
        assert created.status_code == 201
        created_role = created.json()
        role_id = created_role["id"]
        assert len(created_role["responsibilities"]) == 2
        assert created_role["goals"][0]["title"] == "Improve service resilience"
        assert created_role["competencies"][0]["expected_level"] == "Advanced"

        duplicate = client.post(
            "/api/v1/role-catalog/roles",
            json={**payload, "name": " platform reliability lead "},
        )
        assert duplicate.status_code == 409

        current_user_id["value"] = "senior_manager"
        shared_history = client.get("/api/v1/role-catalog/history")
        assert shared_history.status_code == 200
        assert len(shared_history.json()) == 1
        assert shared_history.json()[0]["actor_name"] == "Erin Manager"

        updated_payload = {
            **payload,
            "name": "Principal Reliability Lead",
            "responsibilities": [{"statement": "Guide reliability strategy."}],
            "goals": [{"title": "Reduce incident recurrence", "description": None}],
            "competencies": [],
        }
        updated = client.put(
            f"/api/v1/role-catalog/roles/{role_id}",
            json=updated_payload,
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Principal Reliability Lead"
        assert updated.json()["competencies"] == []

        current_user_id["value"] = "other_manager"
        other_company_payload = {
            **payload,
            "name": "Northstar Platform Reliability Lead",
            "summary": "Visible only to Northstar managers.",
        }
        other_company_created = client.post(
            "/api/v1/role-catalog/roles",
            json=other_company_payload,
        )
        assert other_company_created.status_code == 201
        other_company_role_id = other_company_created.json()["id"]
        other_company_roles = client.get("/api/v1/role-catalog/roles")
        assert other_company_roles.status_code == 200
        assert [role["id"] for role in other_company_roles.json()] == [
            other_company_role_id
        ]
        assert other_company_roles.json()[0]["summary"] == (
            "Visible only to Northstar managers."
        )
        other_company_history = client.get("/api/v1/role-catalog/history")
        assert other_company_history.status_code == 200
        assert [event["role_id"] for event in other_company_history.json()] == [
            other_company_role_id
        ]

        cross_company_update = client.put(
            f"/api/v1/role-catalog/roles/{role_id}",
            json=updated_payload,
        )
        assert cross_company_update.status_code == 404

        current_user_id["value"] = "manager"
        northstar_roles = client.get("/api/v1/role-catalog/roles")
        assert northstar_roles.status_code == 200
        assert [role["id"] for role in northstar_roles.json()] == [role_id]
        northstar_history = client.get("/api/v1/role-catalog/history")
        assert northstar_history.status_code == 200
        assert all(event["role_id"] == role_id for event in northstar_history.json())

        current_user_id["value"] = "employee"
        denied_list = client.get("/api/v1/role-catalog/roles")
        denied_create = client.post("/api/v1/role-catalog/roles", json=payload)
        assert denied_list.status_code == 403
        assert denied_create.status_code == 403

        current_user_id["value"] = "director"
        deleted = client.delete(f"/api/v1/role-catalog/roles/{role_id}")
        assert deleted.status_code == 204

        current_user_id["value"] = "manager"
        remaining_roles = client.get("/api/v1/role-catalog/roles")
        assert remaining_roles.status_code == 200
        assert remaining_roles.json() == []
        history = client.get(
            "/api/v1/role-catalog/history",
            params={"role_id": role_id},
        )
        assert history.status_code == 200
        assert [event["action"] for event in history.json()] == [
            "DELETED",
            "UPDATED",
            "CREATED",
        ]
        assert history.json()[0]["before_snapshot"]["name"] == "Principal Reliability Lead"
        assert history.json()[0]["after_snapshot"] is None
        assert history.json()[1]["before_snapshot"]["name"] == "Platform Reliability Lead"
        assert history.json()[1]["after_snapshot"]["name"] == "Principal Reliability Lead"

        current_user_id["value"] = "other_manager"
        other_company_roles_after_delete = client.get("/api/v1/role-catalog/roles")
        assert other_company_roles_after_delete.status_code == 200
        assert [role["id"] for role in other_company_roles_after_delete.json()] == [
            other_company_role_id
        ]
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        db.close()
        engine.dispose()
