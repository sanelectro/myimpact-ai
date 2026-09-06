from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.evidence_version import get_evidence_version_service
from app.db.models.evidence_version import EvidenceVersionDB
from app.main import app
from app.services.evidence_version import EvidenceVersionService

client = TestClient(app)


def _version(number=1):
    now = datetime.now(UTC)
    return EvidenceVersionDB(id=f"version-{number}", evidence_id="evidence-1", version=number, content=f"v{number}", content_hash=f"hash-{number}", captured_at=now, created_at=now)


def test_create_evidence_version():
    service = MagicMock(spec=EvidenceVersionService)
    service.create_version.return_value = _version()
    app.dependency_overrides[get_evidence_version_service] = lambda: service
    try:
        response = client.post("/evidence-versions", json={"evidence_id": "evidence-1", "content": "v1", "content_hash": "hash-1", "captured_at": datetime.now(UTC).isoformat()})
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


def test_get_version_by_id():
    service = MagicMock(spec=EvidenceVersionService)
    service.get_version_by_id.return_value = _version()
    app.dependency_overrides[get_evidence_version_service] = lambda: service
    try:
        assert client.get("/evidence-versions/version-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_version_by_id_returns_404():
    service = MagicMock(spec=EvidenceVersionService)
    service.get_version_by_id.return_value = None
    app.dependency_overrides[get_evidence_version_service] = lambda: service
    try:
        assert client.get("/evidence-versions/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_versions_by_evidence_id():
    service = MagicMock(spec=EvidenceVersionService)
    service.get_versions_by_evidence_id.return_value = [_version(1), _version(2)]
    app.dependency_overrides[get_evidence_version_service] = lambda: service
    try:
        response = client.get("/evidence-versions/evidence/evidence-1")
        assert response.status_code == 200
        assert [item["version"] for item in response.json()] == [1, 2]
    finally:
        app.dependency_overrides.clear()


def test_get_version_by_evidence_and_version():
    service = MagicMock(spec=EvidenceVersionService)
    service.get_version.return_value = _version(2)
    app.dependency_overrides[get_evidence_version_service] = lambda: service
    try:
        response = client.get("/evidence-versions/evidence/evidence-1/version/2")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_version_by_evidence_and_version_returns_404():
    service = MagicMock(spec=EvidenceVersionService)
    service.get_version.return_value = None
    app.dependency_overrides[get_evidence_version_service] = lambda: service
    try:
        assert client.get("/evidence-versions/evidence/evidence-1/version/99").status_code == 404
    finally:
        app.dependency_overrides.clear()
