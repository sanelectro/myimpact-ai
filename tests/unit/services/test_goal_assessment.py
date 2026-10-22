from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.api_v1_goals import GoalExpectationStatus
from app.models.evidence import EvidenceStatus
from app.services.goal_assessment import GoalAssessmentService


@pytest.mark.parametrize(
    ("evidence_count", "impact_count", "expected_status", "expected_progress"),
    [
        (0, 0, GoalExpectationStatus.NOT_STARTED, 0),
        (1, 0, GoalExpectationStatus.IN_PROGRESS, 0),
        (1, 1, GoalExpectationStatus.IN_PROGRESS, 33),
        (2, 2, GoalExpectationStatus.IN_PROGRESS, 67),
        (3, 3, GoalExpectationStatus.MET, 100),
        (4, 4, GoalExpectationStatus.ABOVE, 133),
    ],
)
def test_assessment_thresholds(evidence_count, impact_count, expected_status, expected_progress):
    service = GoalAssessmentService(MagicMock(spec=Session))
    evidence_ids = [f"evidence-{index}" for index in range(evidence_count)]
    service.mapping_repository.get_by_goal_id = MagicMock(
        return_value=[SimpleNamespace(evidence_id=evidence_id) for evidence_id in evidence_ids]
    )
    service.evidence_repository.get_by_id = MagicMock(
        side_effect=lambda evidence_id: SimpleNamespace(status=EvidenceStatus.ACTIVE)
    )
    service.impact_repository.get_by_goal_id = MagicMock(
        return_value=[
            SimpleNamespace(evidence_id=evidence_id)
            for evidence_id in evidence_ids[:impact_count]
        ]
    )

    assessment = service.assess("goal-1")

    assert assessment.status == expected_status
    assert assessment.achievement_count == evidence_count
    assert assessment.qualifying_achievement_count == impact_count
    assert assessment.progress_percentage == expected_progress


def test_impact_without_goal_evidence_does_not_qualify():
    service = GoalAssessmentService(MagicMock(spec=Session))
    service.mapping_repository.get_by_goal_id = MagicMock(
        return_value=[SimpleNamespace(evidence_id="evidence-1")]
    )
    service.evidence_repository.get_by_id = MagicMock(
        return_value=SimpleNamespace(status=EvidenceStatus.ACTIVE)
    )
    service.impact_repository.get_by_goal_id = MagicMock(
        return_value=[SimpleNamespace(evidence_id="unlinked-evidence")]
    )

    assessment = service.assess("goal-1")

    assert assessment.status == GoalExpectationStatus.IN_PROGRESS
    assert assessment.demonstrated_impact_count == 0
    assert assessment.qualifying_achievement_count == 0


def test_inactive_evidence_does_not_count_toward_assessment():
    service = GoalAssessmentService(MagicMock(spec=Session))
    service.mapping_repository.get_by_goal_id = MagicMock(
        return_value=[SimpleNamespace(evidence_id="evidence-1")]
    )
    service.evidence_repository.get_by_id = MagicMock(
        return_value=SimpleNamespace(status=EvidenceStatus.ARCHIVED)
    )
    service.impact_repository.get_by_goal_id = MagicMock(
        return_value=[SimpleNamespace(evidence_id="evidence-1")]
    )

    assessment = service.assess("goal-1")

    assert assessment.status == GoalExpectationStatus.NOT_STARTED
    assert assessment.achievement_count == 0
    assert assessment.demonstrated_impact_count == 0
    assert assessment.qualifying_achievement_count == 0