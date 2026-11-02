from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, get_current_user
from app.db.base import Base
from app.db.models.organization import OrganizationDB
from app.db.models.team import TeamDB
from app.db.models.threshold_governance import (
    MetricDefinitionDB,
    ThresholdApprovalDB,
    ThresholdAuditEventDB,
    ThresholdItemDB,
    ThresholdSetDB,
)
from app.db.models.user import UserDB
from app.db.session import get_db
from app.evaluation.evaluation_metrics import METRIC_DEFINITIONS
from app.main import app


def _items() -> list[dict]:
    return [
        {
            "metric_id": definition.metric_id,
            "metric_definition_version": definition.definition_version,
            "operator": "<=" if definition.direction.value == "LOWER_IS_BETTER" else ">=",
            "threshold_value": 0.5,
            "unit": definition.unit.value,
            "rationale": f"Synthetic proposal rationale for {definition.metric_id}.",
        }
        for definition in METRIC_DEFINITIONS
    ]


def test_platform_admin_can_propose_and_distinct_admin_can_decide_thresholds():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        OrganizationDB.__table__,
        TeamDB.__table__,
        UserDB.__table__,
        MetricDefinitionDB.__table__,
        ThresholdSetDB.__table__,
        ThresholdItemDB.__table__,
        ThresholdApprovalDB.__table__,
        ThresholdAuditEventDB.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    active_user = {"id": "admin-1"}

    def override_db():
        with Session(engine) as db:
            yield db

    def override_user() -> AuthenticatedUser:
        return AuthenticatedUser(
            active_user["id"],
            f"{active_user['id']}@example.com",
            "Platform Admin",
            {"myimpact-ai"},
            is_platform_admin=True,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    try:
        definitions = client.get("/api/v1/threshold-governance/metric-definitions")
        assert definitions.status_code == 200
        assert {item["metric_id"] for item in definitions.json()} == {
            definition.metric_id for definition in METRIC_DEFINITIONS
        }

        created = client.post(
            "/api/v1/threshold-governance/threshold-sets",
            json={
                "name": "Synthetic threshold proposal",
                "dataset_id": "m66-criterion-assessment-v1",
                "dataset_version": "m66-criterion-assessment-v1",
                "prompt_version": "m66-criterion-assessment-v1",
                "model_identifier": "fixture-model",
                "model_configuration": {"temperature": 0},
                "evaluation_code_version": "test-code",
                "proposal_rationale": "Synthetic test proposal; not an approval.",
                "items": _items(),
            },
        )
        assert created.status_code == 201
        threshold_set_id = created.json()["id"]

        proposed = client.post(
            f"/api/v1/threshold-governance/threshold-sets/{threshold_set_id}/propose"
        )
        assert proposed.status_code == 200
        assert proposed.json()["status"] == "PROPOSED"

        self_decision = client.post(
            f"/api/v1/threshold-governance/threshold-sets/{threshold_set_id}/decision",
            json={
                "decision": "APPROVED",
                "rationale": "Self-approval must be rejected.",
            },
        )
        assert self_decision.status_code == 422

        active_user["id"] = "admin-2"
        decision = client.post(
            f"/api/v1/threshold-governance/threshold-sets/{threshold_set_id}/decision",
            json={
                "decision": "REJECTED",
                "rationale": "Synthetic rejection; not a release decision.",
                "policy_reference": "M66.6.3-test-policy",
            },
        )
        assert decision.status_code == 200
        assert decision.json()["decision"] == "REJECTED"
        assert decision.json()["approver_user_id"] == "admin-2"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()


def test_non_admin_cannot_read_threshold_governance():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "user-1",
        "user@example.com",
        "Software Engineer",
        {"myimpact-ai"},
    )
    try:
        response = TestClient(app).get(
            "/api/v1/threshold-governance/metric-definitions"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
