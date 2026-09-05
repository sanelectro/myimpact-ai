from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.impact_assessment import ImpactAssessmentDB
from app.repositories.impact_assessment import ImpactAssessmentRepository
from datetime import UTC

from app.models.impact_assessment import ImpactType


def test_get_by_id_returns_impact_assessment():
    session = MagicMock(spec=Session)
    expected_assessment = MagicMock(spec=ImpactAssessmentDB)

    session.get.return_value = expected_assessment

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_id("assessment-123")

    assert result is expected_assessment
    session.get.assert_called_once_with(
        ImpactAssessmentDB,
        "assessment-123",
    )


def test_get_by_id_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    session.get.return_value = None

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_id("missing-assessment")

    assert result is None
    session.get.assert_called_once_with(
        ImpactAssessmentDB,
        "missing-assessment",
    )
    
    
def test_get_by_evidence_id_returns_assessments():
    session = MagicMock(spec=Session)

    assessment_1 = MagicMock(spec=ImpactAssessmentDB)
    assessment_2 = MagicMock(spec=ImpactAssessmentDB)

    expected_assessments = [assessment_1, assessment_2]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = expected_assessments

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_evidence_id("evidence-123")

    assert result == expected_assessments
    session.query.assert_called_once_with(ImpactAssessmentDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
    
    
def test_get_by_evidence_id_returns_empty_list_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = []

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_evidence_id("missing-evidence")

    assert result == []
    session.query.assert_called_once_with(ImpactAssessmentDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
    
    
def test_get_by_goal_id_returns_assessments():
    session = MagicMock(spec=Session)

    assessment_1 = MagicMock(spec=ImpactAssessmentDB)
    assessment_2 = MagicMock(spec=ImpactAssessmentDB)

    expected_assessments = [assessment_1, assessment_2]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = expected_assessments

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_goal_id("goal-123")

    assert result == expected_assessments
    session.query.assert_called_once_with(ImpactAssessmentDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()


def test_get_by_goal_id_returns_empty_list_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = []

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_goal_id("missing-goal")

    assert result == []
    session.query.assert_called_once_with(ImpactAssessmentDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
    
    
def test_get_by_evidence_and_goal_returns_assessment():
    session = MagicMock(spec=Session)
    expected_assessment = MagicMock(spec=ImpactAssessmentDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = expected_assessment

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_evidence_and_goal(
        "evidence-123",
        "goal-123",
    )

    assert result is expected_assessment
    session.query.assert_called_once_with(ImpactAssessmentDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()

    filter_arguments = query.filter.call_args.args

    assert len(filter_arguments) == 2
    assert filter_arguments[0].right.value == "evidence-123"
    assert filter_arguments[1].right.value == "goal-123"
    
    
def test_get_by_evidence_and_goal_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = None

    repository = ImpactAssessmentRepository(session)

    result = repository.get_by_evidence_and_goal(
        "missing-evidence",
        "missing-goal",
    )

    assert result is None
    session.query.assert_called_once_with(ImpactAssessmentDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()
    
    
def test_create_impact_assessment():
    session = MagicMock(spec=Session)
    repository = ImpactAssessmentRepository(session)

    result = repository.create(
        assessment_id="assessment-123",
        evidence_id="evidence-123",
        goal_id="goal-123",
        impact_type=ImpactType.RELIABILITY,
        impact_summary="Improved deployment reliability.",
        impact_score=0.9,
        confidence=0.95,
    )

    assert isinstance(result, ImpactAssessmentDB)
    assert result.id == "assessment-123"
    assert result.evidence_id == "evidence-123"
    assert result.goal_id == "goal-123"
    assert result.impact_type == ImpactType.RELIABILITY
    assert result.impact_summary == "Improved deployment reliability."
    assert result.impact_score == 0.9
    assert result.confidence == 0.95
    assert result.assessment_version == 1

    assert result.created_at is not None
    assert result.updated_at is not None
    assert result.created_at.tzinfo == UTC
    assert result.updated_at.tzinfo == UTC

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()
    
def test_create_impact_assessment_with_version():
    session = MagicMock(spec=Session)
    repository = ImpactAssessmentRepository(session)

    result = repository.create(
        assessment_id="assessment-456",
        evidence_id="evidence-123",
        goal_id="goal-123",
        impact_type=ImpactType.RELIABILITY,
        impact_summary="Updated assessment after new evidence.",
        impact_score=0.95,
        confidence=0.98,
        assessment_version=2,
    )

    assert isinstance(result, ImpactAssessmentDB)
    assert result.id == "assessment-456"
    assert result.evidence_id == "evidence-123"
    assert result.goal_id == "goal-123"
    assert result.impact_type == ImpactType.RELIABILITY
    assert result.impact_summary == "Updated assessment after new evidence."
    assert result.impact_score == 0.95
    assert result.confidence == 0.98
    assert result.assessment_version == 2

    assert result.created_at is not None
    assert result.updated_at is not None

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()