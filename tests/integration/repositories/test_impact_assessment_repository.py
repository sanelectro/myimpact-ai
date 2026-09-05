from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.goal import GoalDB
from app.db.models.impact_assessment import ImpactAssessmentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceSourceType
from app.models.impact_assessment import ImpactType
from app.repositories.evidence import EvidenceRepository
from app.repositories.goal import GoalRepository
from app.repositories.impact_assessment import ImpactAssessmentRepository


@pytest.mark.integration
def test_create_and_get_impact_assessment():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    goal_id = f"test-goal-{uuid4()}"
    evidence_id = f"test-evidence-{uuid4()}"
    assessment_id = f"test-assessment-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Impact Assessment Test User",
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

        repository = ImpactAssessmentRepository(session)

        repository.create(
            assessment_id=assessment_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=ImpactType.RELIABILITY,
            impact_summary="Improved deployment reliability.",
            impact_score=0.9,
            confidence=0.95,
        )

        session.commit()

        result_by_id = repository.get_by_id(assessment_id)

        assert result_by_id is not None
        assert result_by_id.id == assessment_id
        assert result_by_id.evidence_id == evidence_id
        assert result_by_id.goal_id == goal_id
        assert result_by_id.impact_type == ImpactType.RELIABILITY
        assert result_by_id.impact_score == 0.9
        assert result_by_id.confidence == 0.95
        assert result_by_id.assessment_version == 1

        evidence_assessments = repository.get_by_evidence_id(evidence_id)

        assert len(evidence_assessments) == 1
        assert evidence_assessments[0].id == assessment_id

        goal_assessments = repository.get_by_goal_id(goal_id)

        assert len(goal_assessments) == 1
        assert goal_assessments[0].id == assessment_id

        result_by_relationship = repository.get_by_evidence_and_goal(
            evidence_id,
            goal_id,
        )

        assert result_by_relationship is not None
        assert result_by_relationship.id == assessment_id

    finally:
        session.execute(
            delete(ImpactAssessmentDB).where(
                ImpactAssessmentDB.id == assessment_id
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
def test_create_multiple_assessment_versions():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    goal_id = f"test-goal-{uuid4()}"
    evidence_id = f"test-evidence-{uuid4()}"
    assessment_1_id = f"test-assessment-{uuid4()}"
    assessment_2_id = f"test-assessment-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Assessment Version Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        GoalRepository(session).create(
            goal_id=goal_id,
            user_id=user_id,
            title="Improve deployment reliability",
        )
        session.commit()

        EvidenceRepository(session).create(
            evidence_id=evidence_id,
            user_id=user_id,
            source_type=EvidenceSourceType.GITHUB,
            title="Deployment monitoring",
            captured_at=datetime.now(UTC),
        )
        session.commit()

        repository = ImpactAssessmentRepository(session)

        repository.create(
            assessment_id=assessment_1_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=ImpactType.RELIABILITY,
            impact_summary="Initial reliability assessment.",
            impact_score=0.80,
            confidence=0.85,
            assessment_version=1,
        )

        repository.create(
            assessment_id=assessment_2_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=ImpactType.RELIABILITY,
            impact_summary="Updated reliability assessment.",
            impact_score=0.95,
            confidence=0.98,
            assessment_version=2,
        )

        session.commit()

        assessments = repository.get_by_evidence_and_goal(
            evidence_id,
            goal_id,
        )

        assert assessments is not None

        all_assessments = repository.get_by_evidence_id(evidence_id)

        assert len(all_assessments) == 2

        versions = {
            assessment.assessment_version
            for assessment in all_assessments
        }

        assert versions == {1, 2}

    finally:
        session.execute(
            delete(ImpactAssessmentDB).where(
                ImpactAssessmentDB.evidence_id == evidence_id
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