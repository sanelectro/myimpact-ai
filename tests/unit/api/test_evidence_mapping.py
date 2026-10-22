from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.evidence_mapping import get_evidence_mapping_service, get_goal_service
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.main import app
from app.models.evidence_mapping import EvidenceRelevance
from app.models.goal import GoalStatus
from app.services.evidence_mapping import EvidenceMappingService
from app.services.goal import GoalService

client = TestClient(app)


def _mapping():
    now = datetime.now(UTC)
    return EvidenceMappingDB(id="mapping-1", evidence_id="evidence-1", goal_id="goal-1", relevance=EvidenceRelevance.HIGH, reason="Direct support", confidence=0.95, created_at=now, updated_at=now)


def test_create_mapping():
    service = MagicMock(spec=EvidenceMappingService)
    service.create_mapping.return_value = _mapping()
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value.status = GoalStatus.ACTIVE
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    try:
        response = client.post("/evidence-mappings", json={"evidence_id": "evidence-1", "goal_id": "goal-1", "relevance": "high", "confidence": 0.95, "reason": "Direct support"})
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


def test_create_mapping_rejects_inactive_goal():
    service = MagicMock(spec=EvidenceMappingService)
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value.status = GoalStatus.APPROVED
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    try:
        response = client.post("/evidence-mappings", json={"evidence_id": "evidence-1", "goal_id": "goal-1", "relevance": "high", "confidence": 0.95})
        assert response.status_code == 409
        assert response.json()["detail"] == "Goal must be active before evidence can be added. Activate it first."
        service.create_mapping.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_create_mapping_returns_409_when_mapping_exists():
    service = MagicMock(spec=EvidenceMappingService)
    service.create_mapping.side_effect = EvidenceMappingAlreadyExistsError("Evidence is already mapped to this goal.")
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value.status = GoalStatus.ACTIVE
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    try:
        response = client.post("/evidence-mappings", json={"evidence_id": "evidence-1", "goal_id": "goal-1", "relevance": "high", "confidence": 0.95})
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_get_mapping_by_id():
    service = MagicMock(spec=EvidenceMappingService)
    service.get_mapping_by_id.return_value = _mapping()
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    try:
        assert client.get("/evidence-mappings/mapping-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_mapping_by_id_returns_404():
    service = MagicMock(spec=EvidenceMappingService)
    service.get_mapping_by_id.return_value = None
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    try:
        assert client.get("/evidence-mappings/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_mappings_by_evidence_id():
    service = MagicMock(spec=EvidenceMappingService)
    service.get_mappings_by_evidence_id.return_value = [_mapping()]
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    try:
        assert client.get("/evidence-mappings/evidence/evidence-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_mappings_by_goal_id():
    service = MagicMock(spec=EvidenceMappingService)
    service.get_mappings_by_goal_id.return_value = [_mapping()]
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    try:
        assert client.get("/evidence-mappings/goal/goal-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_mapping_by_evidence_and_goal():
    service = MagicMock(spec=EvidenceMappingService)
    service.get_mapping_by_evidence_and_goal.return_value = _mapping()
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    try:
        assert client.get("/evidence-mappings/evidence/evidence-1/goal/goal-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_mapping_by_evidence_and_goal_returns_404():
    service = MagicMock(spec=EvidenceMappingService)
    service.get_mapping_by_evidence_and_goal.return_value = None
    app.dependency_overrides[get_evidence_mapping_service] = lambda: service
    try:
        assert client.get("/evidence-mappings/evidence/evidence-1/goal/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()
