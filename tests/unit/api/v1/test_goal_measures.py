from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.v1.goal_measures import get_goal_measures
from app.models.goal import GoalStatus
from app.models.goal_criteria import GoalAssessmentSummaryResponse


def test_counts_only_skips_criterion_assessment():
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = SimpleNamespace(user_id="owner")
    assessment_service = MagicMock()
    db = MagicMock()
    db.execute.return_value.all.return_value = [(GoalStatus.COMPLETED, 2)]

    result = get_goal_measures("goal", "owner", goal_service, assessment_service, db, False)

    assert result.child_execution.total == 2
    assert result.own_criterion_assessment is None
    assessment_service.get_summary.assert_not_called()


def test_default_preserves_criterion_assessment():
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = SimpleNamespace(user_id="owner")
    assessment_service = MagicMock()
    assessment_service.get_summary.return_value = GoalAssessmentSummaryResponse(
        goal_id="goal", run_id=None, run_status=None, criteria_count=0,
        assessed_criteria_count=0, criteria_met_count=0, criteria_met_percentage=None,
        goal_progress_percentage=None, evidence_coverage_percentage=None,
        average_confidence=None, criteria=[], updated_at=None,
    )
    db = MagicMock()
    db.execute.return_value.all.return_value = []

    result = get_goal_measures("goal", "owner", goal_service, assessment_service, db)

    assert result.own_criterion_assessment.goal_id == "goal"
    assessment_service.get_summary.assert_called_once_with("goal")
