from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserCreate
from app.services.user import UserService

client = TestClient(app)


@pytest.mark.integration
def test_evidence_mapping_api_create_and_get():
    session = SessionLocal()
    user_id = None
    goal_id = None
    evidence_id = None
    mapping_id = None
    try:
        user = UserService(session).create_user(UserCreate(name="Mapping API User", email=f"{uuid4()}@example.com"))
        user_id = user.id
        goal_id = client.post("/goals", json={"user_id": user_id, "title": "Improve reliability"}).json()["id"]
        evidence_id = client.post("/evidence", json={"user_id": user_id, "source_type": "github", "title": "Reliability evidence", "captured_at": datetime.now(UTC).isoformat()}).json()["id"]
        response = client.post("/evidence-mappings", json={"evidence_id": evidence_id, "goal_id": goal_id, "relevance": "high", "confidence": 0.95, "reason": "Direct support"})
        assert response.status_code == 201
        mapping_id = response.json()["id"]
        response = client.get(f"/evidence-mappings/evidence/{evidence_id}/goal/{goal_id}")
        assert response.status_code == 200
        assert response.json()["id"] == mapping_id
    finally:
        if mapping_id:
            session.execute(delete(EvidenceMappingDB).where(EvidenceMappingDB.id == mapping_id))
        if evidence_id:
            session.execute(delete(EvidenceDB).where(EvidenceDB.id == evidence_id))
        if goal_id:
            session.execute(delete(GoalDB).where(GoalDB.id == goal_id))
        if user_id:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()
