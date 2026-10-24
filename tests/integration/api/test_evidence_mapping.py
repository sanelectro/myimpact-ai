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
        approved = client.post(
            f"/api/v1/goals/{goal_id}/approve",
            params={"user_id": user_id},
        )
        assert approved.status_code == 200
        activated = client.post(
            f"/api/v1/goals/{goal_id}/activate",
            params={"user_id": user_id},
        )
        assert activated.status_code == 200
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


@pytest.mark.integration
def test_goal_evidence_can_attach_to_goal_or_goal_milestone():
    session = SessionLocal()
    user_id = None
    goal_id = None
    evidence_ids: list[str] = []
    try:
        user = UserService(session).create_user(
            UserCreate(name="Evidence Destination User", email=f"{uuid4()}@example.com")
        )
        user_id = user.id
        goal_id = client.post(
            "/goals",
            json={"user_id": user_id, "title": "Improve release reliability"},
        ).json()["id"]
        assert client.post(
            f"/api/v1/goals/{goal_id}/approve",
            params={"user_id": user_id},
        ).status_code == 200
        assert client.post(
            f"/api/v1/goals/{goal_id}/activate",
            params={"user_id": user_id},
        ).status_code == 200

        milestone_response = client.post(
            f"/api/v1/goals/{goal_id}/milestones",
            params={"user_id": user_id},
            json={"title": "Automate release verification"},
        )
        assert milestone_response.status_code == 201
        milestone_id = milestone_response.json()["id"]

        common_evidence = {
            "description": "Added automated release checks.",
            "source_type": "personal",
            "source_id": None,
            "source_url": None,
            "content_hash": None,
            "captured_at": datetime.now(UTC).isoformat(),
            "relevance": "high",
        }
        direct_response = client.post(
            f"/api/v1/goals/{goal_id}/evidence",
            params={"user_id": user_id},
            json={**common_evidence, "title": "Goal-level evidence"},
        )
        assert direct_response.status_code == 201
        evidence_ids.append(direct_response.json()["evidence_id"])
        assert direct_response.json()["milestone_id"] is None

        milestone_response = client.post(
            f"/api/v1/goals/{goal_id}/evidence",
            params={"user_id": user_id},
            json={
                **common_evidence,
                "title": "Milestone-level evidence",
                "milestone_id": milestone_id,
            },
        )
        assert milestone_response.status_code == 201
        evidence_ids.append(milestone_response.json()["evidence_id"])
        assert milestone_response.json()["milestone_id"] == milestone_id

        listed = client.get(
            f"/api/v1/goals/{goal_id}/evidence",
            params={"user_id": user_id},
        )
        assert listed.status_code == 200
        destinations = {item["title"]: item["milestone_id"] for item in listed.json()}
        assert destinations == {
            "Goal-level evidence": None,
            "Milestone-level evidence": milestone_id,
        }

        archived = client.post(
            f"/api/v1/goals/{goal_id}/milestones/{milestone_id}/archive",
            params={"user_id": user_id},
        )
        assert archived.status_code == 200
        deleted = client.delete(
            f"/api/v1/goals/{goal_id}/milestones/{milestone_id}",
            params={"user_id": user_id},
        )
        assert deleted.status_code == 204

        after_delete = client.get(
            f"/api/v1/goals/{goal_id}/evidence",
            params={"user_id": user_id},
        )
        assert after_delete.status_code == 200
        remaining_destinations = {
            item["title"]: item["milestone_id"] for item in after_delete.json()
        }
        assert remaining_destinations == {
            "Goal-level evidence": None,
            "Milestone-level evidence": None,
        }
    finally:
        if evidence_ids:
            session.execute(delete(EvidenceDB).where(EvidenceDB.id.in_(evidence_ids)))
        if goal_id:
            session.execute(delete(GoalDB).where(GoalDB.id == goal_id))
        if user_id:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()
