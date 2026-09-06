from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserCreate
from app.services.user import UserService

client = TestClient(app)


@pytest.mark.integration
def test_evidence_version_api_creates_and_reads_versions():
    session = SessionLocal()
    user_id = None
    evidence_id = None
    try:
        user = UserService(session).create_user(UserCreate(name="Version API User", email=f"{uuid4()}@example.com"))
        user_id = user.id
        response = client.post("/evidence", json={"user_id": user_id, "source_type": "github", "title": "Versioned evidence", "captured_at": datetime.now(UTC).isoformat()})
        assert response.status_code == 201
        evidence_id = response.json()["id"]
        for content, content_hash in [("Version one", "hash-1"), ("Version two", "hash-2")]:
            response = client.post("/evidence-versions", json={"evidence_id": evidence_id, "content": content, "content_hash": content_hash, "captured_at": datetime.now(UTC).isoformat()})
            assert response.status_code == 201
        response = client.get(f"/evidence-versions/evidence/{evidence_id}")
        assert response.status_code == 200
        assert [item["version"] for item in response.json()] == [1, 2]
        response = client.get(f"/evidence-versions/evidence/{evidence_id}/version/2")
        assert response.status_code == 200
        assert response.json()["content_hash"] == "hash-2"
    finally:
        if evidence_id:
            session.execute(delete(EvidenceVersionDB).where(EvidenceVersionDB.evidence_id == evidence_id))
            session.execute(delete(EvidenceDB).where(EvidenceDB.id == evidence_id))
        if user_id:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()
