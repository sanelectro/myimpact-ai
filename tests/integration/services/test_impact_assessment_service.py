from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.goal import GoalDB
from app.db.models.impact_assessment import ImpactAssessmentDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceCreate, EvidenceSourceType
from app.models.goal import GoalCreate
from app.models.impact_assessment import ImpactType
from app.models.user import UserCreate
from app.services.evidence import EvidenceService
from app.services.goal import GoalService
from app.services.impact_assessment import ImpactAssessmentService
from app.services.user import UserService


@pytest.mark.integration
def test_create_multiple_assessment_versions():
    session = SessionLocal()
    user_id = None
    goal_id = None
    evidence_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Assessment Service User",
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

        service = ImpactAssessmentService(session)

        assessment_1 = service.create_assessment(
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=ImpactType.RELIABILITY,
            impact_summary="Initial reliability improvement.",
            impact_score=0.80,
            confidence=0.85,
        )

        assessment_2 = service.create_assessment(
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=ImpactType.RELIABILITY,
            impact_summary="Improved reliability with stronger evidence.",
            impact_score=0.95,
            confidence=0.98,
        )

        assert assessment_1.assessment_version == 1
        assert assessment_2.assessment_version == 2

        assessments = service.get_assessments_by_evidence_id(evidence_id)

        assert {
            assessment.assessment_version
            for assessment in assessments
            if assessment.goal_id == goal_id
        } == {1, 2}

    finally:
        if evidence_id is not None:
            session.execute(
                delete(ImpactAssessmentDB).where(
                    ImpactAssessmentDB.evidence_id == evidence_id
                )
            )
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
