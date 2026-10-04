from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.evidence import get_goal_service
from app.api.v1.insight import get_career_insight_service, get_impact_assessment_service
from app.models.impact_intelligence import CareerInsight
from app.models.impact_assessment import ImpactType

client = TestClient(app)


def _goal(user_id="user-1"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id="goal-1", user_id=user_id, title="Architecture leadership",
        description="Lead architecture decisions.", created_at=now, updated_at=now,
    )


def _assessment():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id="assessment-1", evidence_id="evidence-1", goal_id="goal-1",
        impact_type=ImpactType.TECHNICAL, impact_summary="Improved architecture.",
        impact_score=0.8, confidence=0.9, created_at=now, updated_at=now,
    )


def _insight_service():
    service = MagicMock()
    service.synthesize = AsyncMock(return_value=CareerInsight(
        goal_id="goal-1", headline="Architecture leadership impact",
        summary="Evidence shows stronger architecture contribution.",
        impact_types=[ImpactType.TECHNICAL],
        supporting_assessment_ids=["assessment-1"], confidence=0.9,
    ))
    return service


def test_goal_insight_enforces_goal_ownership():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal(user_id="owner")
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    try:
        response = client.get("/api/v1/goals/goal-1/insight", params={"user_id": "other-user"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_goal_insight_returns_product_contract():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal()
    impact_service = MagicMock(); impact_service.get_assessments_by_goal_id.return_value = [_assessment()]
    insight_service = _insight_service()
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_impact_assessment_service: lambda: impact_service,
        get_career_insight_service: lambda: insight_service,
    })
    try:
        response = client.get("/api/v1/goals/goal-1/insight", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["headline"] == "Architecture leadership impact"
    assert "assessment-1" in body["supporting_assessment_ids"]
    insight_service.synthesize.assert_awaited_once()


def test_goal_report_returns_product_contract():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal()
    impact_service = MagicMock(); impact_service.get_assessments_by_goal_id.return_value = [_assessment()]
    insight_service = _insight_service()
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_impact_assessment_service: lambda: impact_service,
        get_career_insight_service: lambda: insight_service,
    })
    try:
        response = client.get("/api/v1/goals/goal-1/report", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["goal_id"] == "goal-1"
    assert body["goal_title"] == "Architecture leadership"
    assert body["impact_assessment_count"] == 1
    assert "headline" in body


def test_goal_report_requires_impact_assessments():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal()
    impact_service = MagicMock(); impact_service.get_assessments_by_goal_id.return_value = []
    insight_service = _insight_service()
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_impact_assessment_service: lambda: impact_service,
        get_career_insight_service: lambda: insight_service,
    })
    try:
        response = client.get("/api/v1/goals/goal-1/report", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "HTTP_422"
