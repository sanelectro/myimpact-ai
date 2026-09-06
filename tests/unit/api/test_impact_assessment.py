from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.impact_assessment import get_impact_assessment_service
from app.db.models.impact_assessment import ImpactAssessmentDB
from app.main import app
from app.models.impact_assessment import ImpactType
from app.services.impact_assessment import ImpactAssessmentService

client = TestClient(app)


def _assessment():
    now = datetime.now(UTC)
    return ImpactAssessmentDB(id="assessment-1", evidence_id="evidence-1", goal_id="goal-1", impact_type=ImpactType.RELIABILITY, impact_summary="Improved reliability", impact_score=0.9, confidence=0.95, assessment_version=1, created_at=now, updated_at=now)


def test_create_assessment():
    service = MagicMock(spec=ImpactAssessmentService)
    service.create_assessment.return_value = _assessment()
    app.dependency_overrides[get_impact_assessment_service] = lambda: service
    try:
        response = client.post("/impact-assessments", json={"evidence_id": "evidence-1", "goal_id": "goal-1", "impact_type": "reliability", "impact_summary": "Improved reliability", "impact_score": 0.9, "confidence": 0.95})
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


def test_get_assessment_by_id():
    service = MagicMock(spec=ImpactAssessmentService)
    service.get_assessment_by_id.return_value = _assessment()
    app.dependency_overrides[get_impact_assessment_service] = lambda: service
    try:
        assert client.get("/impact-assessments/assessment-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_assessment_by_id_returns_404():
    service = MagicMock(spec=ImpactAssessmentService)
    service.get_assessment_by_id.return_value = None
    app.dependency_overrides[get_impact_assessment_service] = lambda: service
    try:
        assert client.get("/impact-assessments/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_assessments_by_evidence_id():
    service = MagicMock(spec=ImpactAssessmentService)
    service.get_assessments_by_evidence_id.return_value = [_assessment()]
    app.dependency_overrides[get_impact_assessment_service] = lambda: service
    try:
        assert client.get("/impact-assessments/evidence/evidence-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_assessments_by_goal_id():
    service = MagicMock(spec=ImpactAssessmentService)
    service.get_assessments_by_goal_id.return_value = [_assessment()]
    app.dependency_overrides[get_impact_assessment_service] = lambda: service
    try:
        assert client.get("/impact-assessments/goal/goal-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_assessment_by_evidence_and_goal():
    service = MagicMock(spec=ImpactAssessmentService)
    service.get_assessment_by_evidence_and_goal.return_value = _assessment()
    app.dependency_overrides[get_impact_assessment_service] = lambda: service
    try:
        assert client.get("/impact-assessments/evidence/evidence-1/goal/goal-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_assessment_by_evidence_and_goal_returns_404():
    service = MagicMock(spec=ImpactAssessmentService)
    service.get_assessment_by_evidence_and_goal.return_value = None
    app.dependency_overrides[get_impact_assessment_service] = lambda: service
    try:
        assert client.get("/impact-assessments/evidence/evidence-1/goal/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()
