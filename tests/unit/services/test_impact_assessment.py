from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.db.models.impact_assessment import ImpactAssessmentDB
from app.models.impact_assessment import ImpactType
from app.repositories.impact_assessment import ImpactAssessmentRepository
from app.services.impact_assessment import ImpactAssessmentService


def test_create_assessment_defaults_to_version_one():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ImpactAssessmentRepository)
    repository.get_by_evidence_id.return_value = []
    repository.create.return_value = MagicMock(spec=ImpactAssessmentDB)

    service = ImpactAssessmentService(session)
    service.repository = repository

    with patch(
        "app.services.impact_assessment.uuid4",
        return_value="assessment-1",
    ):
        result = service.create_assessment(
            evidence_id="evidence-1",
            goal_id="goal-1",
            impact_type=ImpactType.RELIABILITY,
            impact_summary="Improved reliability.",
            impact_score=0.9,
            confidence=0.95,
        )

    assert isinstance(result, ImpactAssessmentDB)
    repository.create.assert_called_once_with(
        assessment_id="assessment-1",
        evidence_id="evidence-1",
        goal_id="goal-1",
        impact_type=ImpactType.RELIABILITY,
        impact_summary="Improved reliability.",
        impact_score=0.9,
        confidence=0.95,
        assessment_version=1,
    )
    session.commit.assert_called_once()


def test_create_assessment_increments_matching_version():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ImpactAssessmentRepository)

    assessment_1 = MagicMock(spec=ImpactAssessmentDB)
    assessment_1.goal_id = "goal-1"
    assessment_1.assessment_version = 1

    assessment_3 = MagicMock(spec=ImpactAssessmentDB)
    assessment_3.goal_id = "goal-1"
    assessment_3.assessment_version = 3

    other_goal = MagicMock(spec=ImpactAssessmentDB)
    other_goal.goal_id = "goal-2"
    other_goal.assessment_version = 8

    repository.get_by_evidence_id.return_value = [
        assessment_1,
        assessment_3,
        other_goal,
    ]
    repository.create.return_value = MagicMock(spec=ImpactAssessmentDB)

    service = ImpactAssessmentService(session)
    service.repository = repository

    with patch(
        "app.services.impact_assessment.uuid4",
        return_value="assessment-4",
    ):
        result = service.create_assessment(
            evidence_id="evidence-1",
            goal_id="goal-1",
            impact_type=ImpactType.RELIABILITY,
            impact_summary="Updated assessment.",
            impact_score=0.95,
            confidence=0.98,
        )

    assert isinstance(result, ImpactAssessmentDB)
    repository.create.assert_called_once_with(
        assessment_id="assessment-4",
        evidence_id="evidence-1",
        goal_id="goal-1",
        impact_type=ImpactType.RELIABILITY,
        impact_summary="Updated assessment.",
        impact_score=0.95,
        confidence=0.98,
        assessment_version=4,
    )


def test_create_assessment_accepts_explicit_version():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ImpactAssessmentRepository)
    repository.create.return_value = MagicMock(spec=ImpactAssessmentDB)

    service = ImpactAssessmentService(session)
    service.repository = repository

    with patch(
        "app.services.impact_assessment.uuid4",
        return_value="assessment-5",
    ):
        result = service.create_assessment(
            evidence_id="evidence-1",
            goal_id="goal-1",
            impact_type=ImpactType.TECHNICAL,
            impact_summary="Explicit version.",
            impact_score=0.8,
            confidence=0.9,
            assessment_version=5,
        )

    assert isinstance(result, ImpactAssessmentDB)
    repository.get_by_evidence_id.assert_not_called()
    repository.create.assert_called_once_with(
        assessment_id="assessment-5",
        evidence_id="evidence-1",
        goal_id="goal-1",
        impact_type=ImpactType.TECHNICAL,
        impact_summary="Explicit version.",
        impact_score=0.8,
        confidence=0.9,
        assessment_version=5,
    )


def test_get_assessment_by_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ImpactAssessmentRepository)
    expected = MagicMock(spec=ImpactAssessmentDB)
    repository.get_by_id.return_value = expected

    service = ImpactAssessmentService(session)
    service.repository = repository

    assert service.get_assessment_by_id("assessment-1") is expected
    repository.get_by_id.assert_called_once_with("assessment-1")


def test_get_assessments_by_evidence_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ImpactAssessmentRepository)
    expected = [MagicMock(spec=ImpactAssessmentDB)]
    repository.get_by_evidence_id.return_value = expected

    service = ImpactAssessmentService(session)
    service.repository = repository

    assert service.get_assessments_by_evidence_id("evidence-1") == expected
    repository.get_by_evidence_id.assert_called_once_with("evidence-1")


def test_get_assessments_by_goal_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ImpactAssessmentRepository)
    expected = [MagicMock(spec=ImpactAssessmentDB)]
    repository.get_by_goal_id.return_value = expected

    service = ImpactAssessmentService(session)
    service.repository = repository

    assert service.get_assessments_by_goal_id("goal-1") == expected
    repository.get_by_goal_id.assert_called_once_with("goal-1")


def test_get_assessment_by_evidence_and_goal():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ImpactAssessmentRepository)
    expected = MagicMock(spec=ImpactAssessmentDB)
    repository.get_by_evidence_and_goal.return_value = expected

    service = ImpactAssessmentService(session)
    service.repository = repository

    assert service.get_assessment_by_evidence_and_goal(
        "evidence-1",
        "goal-1",
    ) is expected
    repository.get_by_evidence_and_goal.assert_called_once_with(
        "evidence-1",
        "goal-1",
    )
