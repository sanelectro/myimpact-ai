from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.evidence import get_evidence_service, get_evidence_mapping_service, get_goal_service
from app.api.v1.impact import get_expectation_service, get_pipeline, get_document_service, get_impact_assessment_service
from app.models.impact_intelligence import CareerInsight
from app.services.knowledge.impact_intelligence_pipeline import ImpactIntelligencePipelineResult

client = TestClient(app)


def _goal(user_id="user-1"):
    now = datetime.now(UTC)
    return SimpleNamespace(id="goal-1", user_id=user_id, title="Architecture", description="Lead architecture", created_at=now, updated_at=now)


def _evidence():
    now = datetime.now(UTC)
    return SimpleNamespace(id="e-1", user_id="user-1", title="Architecture improvement", description="Improved architecture", source_type=SimpleNamespace(value="document"), captured_at=now)


def test_goal_evidence_enforces_goal_ownership():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal("owner")
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    try:
        response = client.get("/api/v1/goals/goal-1/evidence", params={"user_id": "other"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_goal_evidence_returns_product_contract():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal()
    evidence_service = MagicMock(); evidence_service.get_evidence_by_id.return_value = _evidence()
    mapping_service = MagicMock(); mapping_service.get_mappings_by_goal_id.return_value = [SimpleNamespace(evidence_id="e-1", relevance=SimpleNamespace(value="high"), confidence=0.9, reason="Direct support")]
    app.dependency_overrides.update({get_goal_service: lambda: goal_service, get_evidence_service: lambda: evidence_service, get_evidence_mapping_service: lambda: mapping_service})
    try:
        response = client.get("/api/v1/goals/goal-1/evidence", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()[0]
    assert body["evidence_id"] == "e-1"
    assert "user_id" not in body


def test_get_goal_impact_enforces_goal_ownership():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal("owner")
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    try:
        response = client.get("/api/v1/goals/goal-1/impact", params={"user_id": "other"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404


def test_analyze_goal_impact_returns_pipeline_result():
    goal_service = MagicMock(); goal_service.get_goal_by_id.return_value = _goal()
    document_service = MagicMock(); document_service.get_document_by_id.return_value = SimpleNamespace(id="doc-1", user_id="user-1")
    expectation_service = MagicMock(); expectation_service.get_by_document_id.return_value = []
    pipeline = MagicMock()
    pipeline.run = AsyncMock(return_value=ImpactIntelligencePipelineResult(
        career_insight=CareerInsight(goal_id="goal-1", headline="Architecture impact", summary="Strong architecture contribution", confidence=0.9),
        processed_expectations=1, discovered_candidates=2, evaluated_candidates=2, persisted_evidence_count=1, impact_assessment_count=1,
    ))
    now = datetime.now(UTC)
    expectation_service.get_by_document_id.return_value = [SimpleNamespace(id="exp-1", document_id="doc-1", category="architecture", description="Lead architecture", evidence_hints=[], confidence=0.9, created_at=now, updated_at=now)]
    app.dependency_overrides.update({get_goal_service: lambda: goal_service, get_document_service: lambda: document_service, get_expectation_service: lambda: expectation_service, get_pipeline: lambda: pipeline})
    try:
        response = client.post("/api/v1/goals/goal-1/impact/analyze", params={"user_id": "user-1"}, json={"document_ids": ["doc-1"]})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["goal_id"] == "goal-1"
    assert body["impact_assessment_count"] == 1
