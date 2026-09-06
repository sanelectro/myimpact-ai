from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.evidence import get_evidence_service
from app.db.models.evidence import EvidenceDB
from app.main import app
from app.models.evidence import EvidenceSourceType, EvidenceStatus
from app.services.evidence import EvidenceService

client = TestClient(app)


def _evidence():
    now = datetime.now(UTC)
    return EvidenceDB(
        id="evidence-1", user_id="user-1", source_type=EvidenceSourceType.GITHUB,
        source_id="PR-123", title="Monitoring improvement", captured_at=now,
        status=EvidenceStatus.ACTIVE, created_at=now, updated_at=now,
    )


def test_create_evidence():
    service = MagicMock(spec=EvidenceService)
    service.create_evidence.return_value = _evidence()
    app.dependency_overrides[get_evidence_service] = lambda: service
    try:
        response = client.post("/evidence", json={"user_id": "user-1", "source_type": "github", "source_id": "PR-123", "title": "Monitoring improvement", "captured_at": datetime.now(UTC).isoformat()})
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


def test_get_evidence_by_id():
    service = MagicMock(spec=EvidenceService)
    service.get_evidence_by_id.return_value = _evidence()
    app.dependency_overrides[get_evidence_service] = lambda: service
    try:
        response = client.get("/evidence/evidence-1")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_evidence_by_id_returns_404():
    service = MagicMock(spec=EvidenceService)
    service.get_evidence_by_id.return_value = None
    app.dependency_overrides[get_evidence_service] = lambda: service
    try:
        assert client.get("/evidence/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_evidence_by_user_id():
    service = MagicMock(spec=EvidenceService)
    service.get_evidence_by_user_id.return_value = [_evidence()]
    app.dependency_overrides[get_evidence_service] = lambda: service
    try:
        response = client.get("/evidence/user/user-1")
        assert response.status_code == 200
        assert len(response.json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_get_evidence_by_source():
    service = MagicMock(spec=EvidenceService)
    service.get_evidence_by_source.return_value = _evidence()
    app.dependency_overrides[get_evidence_service] = lambda: service
    try:
        response = client.get("/evidence/source", params={"source_type": "github", "source_id": "PR-123"})
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_evidence_by_source_returns_404():
    service = MagicMock(spec=EvidenceService)
    service.get_evidence_by_source.return_value = None
    app.dependency_overrides[get_evidence_service] = lambda: service
    try:
        response = client.get("/evidence/source", params={"source_type": "github", "source_id": "missing"})
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
