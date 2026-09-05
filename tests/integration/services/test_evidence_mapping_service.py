from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceCreate, EvidenceSourceType
from app.models.evidence_mapping import EvidenceRelevance
from app.models.goal import GoalCreate
from app.models.user import UserCreate
from app.services.evidence import EvidenceService
from app.services.evidence_mapping import EvidenceMappingService
from app.services.goal import GoalService
from app.services.user import UserService


@pytest.mark.integration
def test_create_and_get_evidence_mapping():
    session = SessionLocal()
    user_id = None
    goal_id = None
    evidence_id = None
    mapping_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Mapping Service User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        goal = GoalService(session).create_goal(
            GoalCreate(
                user_id=user_id,
                title="Improve reliability",
            )
        )
        goal_id = goal.id

        evidence = EvidenceService(session).create_evidence(
            EvidenceCreate(
                user_id=user_id,
                source_type=EvidenceSourceType.GITHUB,
                title="Monitoring improvement",
                captured_at=datetime.now(UTC),
            )
        )
        evidence_id = evidence.id

        service = EvidenceMappingService(session)
        mapping = service.create_mapping(
            evidence_id=evidence_id,
            goal_id=goal_id,
            relevance=EvidenceRelevance.HIGH,
            confidence=0.95,
            reason="Directly supports reliability.",
        )
        mapping_id = mapping.id

        result = service.get_mapping_by_evidence_and_goal(
            evidence_id,
            goal_id,
        )

        assert result is not None
        assert result.id == mapping_id
        assert result.relevance == EvidenceRelevance.HIGH

    finally:
        if mapping_id is not None:
            session.execute(
                delete(EvidenceMappingDB).where(
                    EvidenceMappingDB.id == mapping_id
                )
            )
        if evidence_id is not None:
            session.execute(
                delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
            )
        if goal_id is not None:
            session.execute(
                delete(GoalDB).where(GoalDB.id == goal_id)
            )
        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
        session.commit()
        session.close()
