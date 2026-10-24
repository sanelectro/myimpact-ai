from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.models.evidence import EvidenceStatus
from app.api.v1.evidence import (
    get_evidence_mapping_service,
    get_evidence_service,
    get_goal_service,
    get_milestone_service,
)
from app.api.v1.impact import get_expectation_service, get_pipeline, get_document_service, get_impact_assessment_service
from app.db.session import get_db
from app.models.impact_intelligence import CareerInsight
from app.services.knowledge.impact_intelligence_pipeline import ImpactIntelligencePipelineResult

client = TestClient(app)


def _goal(user_id="user-1"):
    now = datetime.now(UTC)
    return SimpleNamespace(id="goal-1", user_id=user_id, title="Architecture", description="Lead architecture", created_at=now, updated_at=now)


def _evidence():
    now = datetime.now(UTC)
    return SimpleNamespace(id="e-1", user_id="user-1", title="Architecture improvement", description="Improved architecture", source_type=SimpleNamespace(value="document"), source_url="https://teams.microsoft.com/l/meetup", captured_at=now, source_updated_at=None, status=EvidenceStatus.ACTIVE)


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
    mapping_service = MagicMock(); mapping_service.get_mappings_by_goal_id.return_value = [SimpleNamespace(id="mapping-1", evidence_id="e-1", milestone_id="milestone-1", relevance=SimpleNamespace(value="high"), confidence=0.9, reason="Direct support")]
    db = MagicMock(); db.scalar.return_value = None
    app.dependency_overrides.update({get_goal_service: lambda: goal_service, get_evidence_service: lambda: evidence_service, get_evidence_mapping_service: lambda: mapping_service, get_db: lambda: db})
    try:
        response = client.get("/api/v1/goals/goal-1/evidence", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()[0]
    assert body["evidence_id"] == "e-1"
    assert body["milestone_id"] == "milestone-1"
    assert body["source_url"] == "https://teams.microsoft.com/l/meetup"
    assert "user_id" not in body


def test_create_goal_evidence_rejects_duplicate_title():
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = _goal()
    existing = _evidence()
    mapping_service = MagicMock()
    mapping_service.get_mappings_by_goal_id.return_value = [
        SimpleNamespace(evidence_id=existing.id)
    ]
    evidence_service = MagicMock()
    evidence_service.get_evidence_by_id.return_value = existing
    milestone_service = MagicMock()
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_evidence_service: lambda: evidence_service,
        get_evidence_mapping_service: lambda: mapping_service,
        get_milestone_service: lambda: milestone_service,
    })
    try:
        response = client.post(
            "/api/v1/goals/goal-1/evidence",
            params={"user_id": "user-1"},
            json={
                "title": "  ARCHITECTURE   IMPROVEMENT ",
                "description": "Another description",
                "source_type": "personal",
                "source_id": None,
                "source_url": None,
                "content_hash": None,
                "captured_at": datetime.now(UTC).isoformat(),
                "relevance": "high",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "already attached to this goal" in response.json()["error"]["message"]
    evidence_service.create_evidence.assert_not_called()


def test_create_goal_evidence_reuses_existing_source_for_another_goal():
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = _goal()
    mapping_service = MagicMock()
    mapping_service.get_mappings_by_goal_id.return_value = []
    mapping_service.create_mapping.return_value = SimpleNamespace(
        id="mapping-1",
        milestone_id=None,
        relevance=SimpleNamespace(value="high"),
        confidence=1.0,
        reason="Added by the user",
    )
    existing = _evidence()
    evidence_service = MagicMock()
    evidence_service.get_evidence_by_source.return_value = existing
    milestone_service = MagicMock()
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_evidence_service: lambda: evidence_service,
        get_evidence_mapping_service: lambda: mapping_service,
        get_milestone_service: lambda: milestone_service,
    })
    try:
        response = client.post(
            "/api/v1/goals/goal-1/evidence",
            params={"user_id": "user-1"},
            json={
                "title": "Architecture improvement",
                "description": None,
                "source_type": "document",
                "source_id": "e-1",
                "source_url": existing.source_url,
                "content_hash": None,
                "captured_at": datetime.now(UTC).isoformat(),
                "relevance": "high",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["evidence_id"] == existing.id
    evidence_service.create_evidence.assert_not_called()
    mapping_service.create_mapping.assert_called_once()


def test_create_goal_evidence_attaches_to_owned_milestone():
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = _goal()
    mapping_service = MagicMock()
    mapping_service.get_mappings_by_goal_id.return_value = []
    mapping_service.create_mapping.return_value = SimpleNamespace(
        id="mapping-2",
        milestone_id="milestone-1",
        relevance=SimpleNamespace(value="high"),
        confidence=1.0,
        reason="Added by the user",
    )
    evidence_service = MagicMock()
    evidence_service.create_evidence.return_value = _evidence()
    milestone_service = MagicMock()
    milestone_service.get_milestone_by_id_and_goal.return_value = SimpleNamespace(
        id="milestone-1",
        goal_id="goal-1",
        archived_at=None,
    )
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_evidence_service: lambda: evidence_service,
        get_evidence_mapping_service: lambda: mapping_service,
        get_milestone_service: lambda: milestone_service,
    })
    try:
        response = client.post(
            "/api/v1/goals/goal-1/evidence",
            params={"user_id": "user-1"},
            json={
                "title": "Milestone evidence",
                "description": "Completed verification automation",
                "source_type": "personal",
                "source_id": None,
                "source_url": None,
                "content_hash": None,
                "captured_at": datetime.now(UTC).isoformat(),
                "relevance": "high",
                "milestone_id": "milestone-1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["milestone_id"] == "milestone-1"
    assert mapping_service.create_mapping.call_args.kwargs["milestone_id"] == "milestone-1"


def test_create_goal_evidence_rejects_milestone_not_owned_by_goal():
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = _goal()
    evidence_service = MagicMock()
    mapping_service = MagicMock()
    milestone_service = MagicMock()
    milestone_service.get_milestone_by_id_and_goal.return_value = None
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_evidence_service: lambda: evidence_service,
        get_evidence_mapping_service: lambda: mapping_service,
        get_milestone_service: lambda: milestone_service,
    })
    try:
        response = client.post(
            "/api/v1/goals/goal-1/evidence",
            params={"user_id": "user-1"},
            json={
                "title": "Cross-goal milestone evidence",
                "description": None,
                "source_type": "personal",
                "source_id": None,
                "source_url": None,
                "content_hash": None,
                "captured_at": datetime.now(UTC).isoformat(),
                "relevance": "medium",
                "milestone_id": "other-goal-milestone",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    evidence_service.create_evidence.assert_not_called()
    mapping_service.create_mapping.assert_not_called()


def test_create_goal_evidence_rejects_archived_milestone():
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = _goal()
    evidence_service = MagicMock()
    mapping_service = MagicMock()
    milestone_service = MagicMock()
    milestone_service.get_milestone_by_id_and_goal.return_value = SimpleNamespace(
        id="milestone-1",
        goal_id="goal-1",
        archived_at=datetime.now(UTC),
    )
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_evidence_service: lambda: evidence_service,
        get_evidence_mapping_service: lambda: mapping_service,
        get_milestone_service: lambda: milestone_service,
    })
    try:
        response = client.post(
            "/api/v1/goals/goal-1/evidence",
            params={"user_id": "user-1"},
            json={
                "title": "Archived milestone evidence",
                "description": None,
                "source_type": "personal",
                "source_id": None,
                "source_url": None,
                "content_hash": None,
                "captured_at": datetime.now(UTC).isoformat(),
                "relevance": "medium",
                "milestone_id": "milestone-1",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    evidence_service.create_evidence.assert_not_called()
    mapping_service.create_mapping.assert_not_called()


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
