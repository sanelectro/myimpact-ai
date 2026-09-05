from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserCreate
from app.services.user import UserService

client = TestClient(app)


@pytest.mark.integration
def test_evidence_api_create_and_get():
    session = SessionLocal()
    user_id = None
    evidence_id = None
    try:
        user = UserService(session).create_user(UserCreate(name="Evidence API User", email=f"{uuid4()}@example.com"))
        user_id = user.id
        response = client.post("/evidence", json={"user_id": user_id, "source_type": "github", "source_id": "PR-123", "title": "Monitoring improvement", "captured_at": datetime.now(UTC).isoformat()})
        assert response.status_code == 201
        evidence_id = response.json()["id"]
        response = client.get(f"/evidence/{evidence_id}")
        assert response.status_code == 200
        assert response.json()["user_id"] == user_id
    finally:
        if evidence_id:
            session.execute(delete(EvidenceDB).where(EvidenceDB.id == evidence_id))
        if user_id:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()


@pytest.mark.integration
def test_evidence_api_get_by_source():
    session = SessionLocal()
    user_id = None
    evidence_id = None
    try:
        user = UserService(session).create_user(UserCreate(name="Evidence Source User", email=f"{uuid4()}@example.com"))
        user_id = user.id
        response = client.post("/evidence", json={"user_id": user_id, "source_type": "github", "source_id": "PR-456", "title": "Source lookup", "captured_at": datetime.now(UTC).isoformat()})
        evidence_id = response.json()["id"]
        response = client.get("/evidence/source", params={"source_type": "github", "source_id": "PR-456"})
        assert response.status_code == 200
        assert response.json()["id"] == evidence_id
    finally:
        if evidence_id:
            session.execute(delete(EvidenceDB).where(EvidenceDB.id == evidence_id))
        if user_id:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()


@pytest.mark.integration
def test_evidence_api_missing_returns_404():
    assert client.get("/evidence/missing-evidence").status_code == 404
