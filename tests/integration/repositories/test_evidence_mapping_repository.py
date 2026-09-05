from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceSourceType
from app.models.evidence_mapping import EvidenceRelevance
from app.repositories.evidence import EvidenceRepository
from app.repositories.evidence_mapping import EvidenceMappingRepository
from app.repositories.goal import GoalRepository


@pytest.mark.integration
def test_create_and_get_evidence_mapping():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    goal_id = f"test-goal-{uuid4()}"
    evidence_id = f"test-evidence-{uuid4()}"
    mapping_id = f"test-mapping-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Evidence Mapping Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        goal_repository = GoalRepository(session)

        goal_repository.create(
            goal_id=goal_id,
            user_id=user_id,
            title="Improve deployment reliability",
        )

        session.commit()

        evidence_repository = EvidenceRepository(session)

        evidence_repository.create(
            evidence_id=evidence_id,
            user_id=user_id,
            source_type=EvidenceSourceType.GITHUB,
            source_id=f"PR-{uuid4()}",
            title="Implemented deployment monitoring",
            captured_at=datetime.now(UTC),
        )

        session.commit()

        repository = EvidenceMappingRepository(session)

        repository.create(
            mapping_id=mapping_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            relevance=EvidenceRelevance.HIGH,
            confidence=0.95,
            reason="Evidence directly supports the reliability goal.",
        )

        session.commit()

        result_by_id = repository.get_by_id(mapping_id)

        assert result_by_id is not None
        assert result_by_id.id == mapping_id
        assert result_by_id.evidence_id == evidence_id
        assert result_by_id.goal_id == goal_id
        assert result_by_id.relevance == EvidenceRelevance.HIGH
        assert result_by_id.confidence == 0.95

        evidence_mappings = repository.get_by_evidence_id(evidence_id)

        assert len(evidence_mappings) == 1
        assert evidence_mappings[0].id == mapping_id

        goal_mappings = repository.get_by_goal_id(goal_id)

        assert len(goal_mappings) == 1
        assert goal_mappings[0].id == mapping_id

        result_by_relationship = repository.get_by_evidence_and_goal(
            evidence_id,
            goal_id,
        )

        assert result_by_relationship is not None
        assert result_by_relationship.id == mapping_id

    finally:
        session.execute(
            delete(EvidenceMappingDB).where(
                EvidenceMappingDB.id == mapping_id
            )
        )
        session.execute(
            delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
        )
        session.execute(
            delete(GoalDB).where(GoalDB.id == goal_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()
        
        
@pytest.mark.integration
def test_create_duplicate_evidence_goal_mapping_fails():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    goal_id = f"test-goal-{uuid4()}"
    evidence_id = f"test-evidence-{uuid4()}"
    mapping_1_id = f"test-mapping-{uuid4()}"
    mapping_2_id = f"test-mapping-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Duplicate Mapping Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        goal_repository = GoalRepository(session)

        goal_repository.create(
            goal_id=goal_id,
            user_id=user_id,
            title="Improve deployment reliability",
        )

        session.commit()

        evidence_repository = EvidenceRepository(session)

        evidence_repository.create(
            evidence_id=evidence_id,
            user_id=user_id,
            source_type=EvidenceSourceType.GITHUB,
            title="Implemented deployment monitoring",
            captured_at=datetime.now(UTC),
        )

        session.commit()

        repository = EvidenceMappingRepository(session)

        repository.create(
            mapping_id=mapping_1_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            relevance=EvidenceRelevance.HIGH,
            confidence=0.95,
            reason="First mapping",
        )

        session.commit()

        with pytest.raises(IntegrityError):
            repository.create(
                mapping_id=mapping_2_id,
                evidence_id=evidence_id,
                goal_id=goal_id,
                relevance=EvidenceRelevance.MEDIUM,
                confidence=0.80,
                reason="Duplicate mapping",
            )

        session.rollback()

    finally:
        session.execute(
            delete(EvidenceMappingDB).where(
                EvidenceMappingDB.evidence_id == evidence_id
            )
        )
        session.execute(
            delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
        )
        session.execute(
            delete(GoalDB).where(GoalDB.id == goal_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()