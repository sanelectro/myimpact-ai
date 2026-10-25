import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.db.models.goal_source_retrieval import GoalSourceRetrievalDB
from app.exceptions import GoalCriterionAssessmentError
from app.models.goal_criteria import (
    GoalCriterionAssessmentProposal,
    GoalAssessmentFeedbackType,
    GoalAssessmentRunStatus,
    GoalCriterionDefinition,
    GoalCriterionMilestone,
    GoalCriterionResult,
    GoalSourceRetrievalStatus,
    GoalCriterionType,
)
from app.services.goal_assessment import GoalAssessmentService


@pytest.mark.parametrize(
    ("result", "expected_progress"),
    [
        (GoalCriterionResult.MET, 100),
        (GoalCriterionResult.IN_PROGRESS, 0),
        (GoalCriterionResult.NOT_STARTED, 0),
    ],
)
def test_binary_progress_is_deterministic(result, expected_progress):
    definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Complete the migration",
        completion_conditions="The production migration is complete and verified.",
    )
    proposal = GoalCriterionAssessmentProposal(
        result=result,
        rationale="Assessment rationale",
        confidence=0.8,
    )

    actual_result, progress = GoalAssessmentService._calculate_progress(
        definition,
        proposal,
    )

    assert actual_result == result
    assert progress == expected_progress


def test_needs_review_has_no_invented_progress():
    definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Complete the migration",
        completion_conditions="The production migration is complete and verified.",
    )
    proposal = GoalCriterionAssessmentProposal(
        result=GoalCriterionResult.NEEDS_REVIEW,
        rationale="The evidence is contradictory.",
        confidence=0.4,
    )

    actual_result, progress = GoalAssessmentService._calculate_progress(
        definition,
        proposal,
    )

    assert actual_result == GoalCriterionResult.NEEDS_REVIEW
    assert progress is None


def test_failed_source_retrieval_records_reason_and_snapshot_usage():
    session = Mock()
    service = GoalAssessmentService(session)
    snapshot_captured_at = datetime.now(UTC)
    failure_reason = "GitHub API rate limit exceeded."

    service._record_source_retrieval(
        "goal-1",
        "run-1",
        "github",
        GoalSourceRetrievalStatus.FAILURE,
        failure_reason,
        snapshot_captured_at,
    )

    retrieval = session.add.call_args.args[0]
    assert isinstance(retrieval, GoalSourceRetrievalDB)
    assert retrieval.failure_reason == failure_reason
    assert retrieval.used_snapshot is True
    assert retrieval.snapshot_captured_at == snapshot_captured_at


def test_milestone_progress_uses_equal_weights_and_validates_ids():
    definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.MILESTONE_BASED,
        description="Deliver the platform migration",
        milestones=[
            GoalCriterionMilestone(
                id="design",
                title="Design",
                completion_conditions="Design is approved.",
            ),
            GoalCriterionMilestone(
                id="delivery",
                title="Delivery",
                completion_conditions="The migration is deployed.",
            ),
        ],
    )
    proposal = GoalCriterionAssessmentProposal(
        result=GoalCriterionResult.IN_PROGRESS,
        rationale="The design milestone is complete.",
        confidence=0.8,
        completed_milestone_ids=["design"],
    )

    result, progress = GoalAssessmentService._calculate_progress(
        definition,
        proposal,
    )

    assert result == GoalCriterionResult.IN_PROGRESS
    assert progress == 50


def test_milestone_assessment_rejects_unknown_ids():
    definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.MILESTONE_BASED,
        description="Deliver the platform migration",
        milestones=[
            GoalCriterionMilestone(
                id="design",
                title="Design",
                completion_conditions="Design is approved.",
            ),
        ],
    )
    proposal = GoalCriterionAssessmentProposal(
        result=GoalCriterionResult.MET,
        rationale="Assessment rationale",
        confidence=0.9,
        completed_milestone_ids=["not-a-milestone"],
    )

    with pytest.raises(GoalCriterionAssessmentError, match="milestone reference"):
        GoalAssessmentService._calculate_progress(definition, proposal)


def test_milestone_assessment_rejects_duplicate_completed_ids():
    definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.MILESTONE_BASED,
        description="Deliver the platform migration",
        milestones=[
            GoalCriterionMilestone(
                id="design",
                title="Design",
                completion_conditions="Design is approved.",
            ),
            GoalCriterionMilestone(
                id="delivery",
                title="Delivery",
                completion_conditions="The migration is deployed.",
            ),
        ],
    )
    proposal = GoalCriterionAssessmentProposal(
        result=GoalCriterionResult.IN_PROGRESS,
        rationale="The design milestone is complete.",
        confidence=0.8,
        completed_milestone_ids=["design", "design"],
    )

    with pytest.raises(GoalCriterionAssessmentError, match="milestone reference"):
        GoalAssessmentService._calculate_progress(definition, proposal)


@pytest.mark.parametrize(
    ("measured_value", "expected_result", "expected_progress"),
    [
        (40, GoalCriterionResult.IN_PROGRESS, 40),
        (120, GoalCriterionResult.MET, 100),
        (0, GoalCriterionResult.NOT_STARTED, 0),
    ],
)
def test_measurable_target_progress_is_backend_calculated(
    measured_value,
    expected_result,
    expected_progress,
):
    definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.MEASURABLE_TARGET,
        description="Increase test coverage",
        completion_conditions="Test coverage reaches the defined target.",
        target_value=100,
        unit="percent",
    )
    proposal = GoalCriterionAssessmentProposal(
        result=expected_result,
        rationale="The measurement is supported by the evidence.",
        confidence=0.85,
        measured_value=measured_value,
    )

    actual_result, progress = GoalAssessmentService._calculate_progress(
        definition,
        proposal,
    )

    assert actual_result == expected_result
    assert progress == expected_progress


def test_measurable_target_needs_review_when_value_is_not_supported():
    definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.MEASURABLE_TARGET,
        description="Increase test coverage",
        completion_conditions="Test coverage reaches the defined target.",
        target_value=100,
        unit="percent",
    )
    proposal = GoalCriterionAssessmentProposal(
        result=GoalCriterionResult.NEEDS_REVIEW,
        rationale="The evidence does not include a current measurement.",
        confidence=0.3,
    )

    result, progress = GoalAssessmentService._calculate_progress(
        definition,
        proposal,
    )

    assert result == GoalCriterionResult.NEEDS_REVIEW
    assert progress is None


def test_criterion_definition_requires_type_specific_fields():
    with pytest.raises(ValueError, match="greater than zero"):
        GoalCriterionDefinition(
            criterion_type=GoalCriterionType.MEASURABLE_TARGET,
            description="Increase test coverage",
            completion_conditions="Coverage reaches target.",
            target_value=0,
            unit="percent",
        )


@pytest.mark.parametrize("result", ["MET", "IN_PROGRESS"])
def test_progress_assessment_requires_supporting_evidence_citation(result):
    class AssessmentLLM:
        async def generate(self, _request):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "result": result,
                        "rationale": "The evidence suggests partial progress.",
                        "confidence": 0.8,
                        "supporting_mapping_ids": [],
                        "contradictory_mapping_ids": [],
                        "completed_milestone_ids": [],
                        "measured_value": None,
                        "limitations": [],
                    }
                ),
                model="test-model",
            )

    service = GoalAssessmentService(Mock(), AssessmentLLM())
    version = SimpleNamespace(
        id="version-1",
        version=1,
        definition={
            "criterion_type": "BINARY",
            "description": "Complete the migration",
            "completion_conditions": "The production migration is complete.",
            "milestones": [],
            "target_value": None,
            "unit": None,
            "evidence_suggestions": [],
            "assumptions_and_clarifications": [],
        },
    )

    with pytest.raises(GoalCriterionAssessmentError, match="supporting evidence"):
        asyncio.run(
            service._assess_criterion(
                run=SimpleNamespace(id="run-1"),
                goal=SimpleNamespace(id="goal-1"),
                criterion=SimpleNamespace(id="criterion-1"),
                version=version,
                evidence_inputs=[{"mapping_id": "mapping-1", "content": "Evidence text"}],
            )
        )


def test_assessment_rejects_malformed_llm_output():
    class AssessmentLLM:
        async def generate(self, _request):
            return SimpleNamespace(content='{"result":', model="test-model")

    service = GoalAssessmentService(Mock(), AssessmentLLM())
    version = SimpleNamespace(
        id="version-1",
        version=1,
        definition={
            "criterion_type": "BINARY",
            "description": "Complete the migration",
            "completion_conditions": "The production migration is complete.",
            "milestones": [],
            "target_value": None,
            "unit": None,
            "evidence_suggestions": [],
            "assumptions_and_clarifications": [],
        },
    )

    with pytest.raises(GoalCriterionAssessmentError, match="invalid response"):
        asyncio.run(
            service._assess_criterion(
                run=SimpleNamespace(id="run-1"),
                goal=SimpleNamespace(id="goal-1"),
                criterion=SimpleNamespace(id="criterion-1"),
                version=version,
                evidence_inputs=[{"mapping_id": "mapping-1", "content": "Evidence text"}],
            )
        )


@pytest.mark.parametrize(
    ("supporting_mapping_ids", "contradictory_mapping_ids"),
    [
        (["unknown-mapping"], []),
        ([], ["unknown-mapping"]),
        (["mapping-1"], ["mapping-1"]),
    ],
)
def test_assessment_rejects_unknown_or_conflicting_evidence_citations(
    supporting_mapping_ids,
    contradictory_mapping_ids,
):
    class AssessmentLLM:
        async def generate(self, _request):
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "result": "MET",
                        "rationale": "Assessment rationale.",
                        "confidence": 0.8,
                        "supporting_mapping_ids": supporting_mapping_ids,
                        "contradictory_mapping_ids": contradictory_mapping_ids,
                        "completed_milestone_ids": [],
                        "measured_value": None,
                        "limitations": [],
                    }
                ),
                model="test-model",
            )

    service = GoalAssessmentService(Mock(), AssessmentLLM())
    version = SimpleNamespace(
        id="version-1",
        version=1,
        definition={
            "criterion_type": "BINARY",
            "description": "Complete the migration",
            "completion_conditions": "The production migration is complete.",
            "milestones": [],
            "target_value": None,
            "unit": None,
            "evidence_suggestions": [],
            "assumptions_and_clarifications": [],
        },
    )

    with pytest.raises(GoalCriterionAssessmentError, match="unsupported evidence reference"):
        asyncio.run(
            service._assess_criterion(
                run=SimpleNamespace(id="run-1"),
                goal=SimpleNamespace(id="goal-1"),
                criterion=SimpleNamespace(id="criterion-1"),
                version=version,
                evidence_inputs=[{"mapping_id": "mapping-1", "content": "Evidence text"}],
            )
        )


def test_feedback_records_employee_decision_without_mutating_assessment():
    assessment = SimpleNamespace(
        id="assessment-1",
        criterion_id="criterion-1",
        criterion=SimpleNamespace(goal_id="goal-1"),
        result=GoalCriterionResult.MET,
    )
    service = GoalAssessmentService(Mock())
    service.session.get.return_value = SimpleNamespace(user_id="user-1")
    service.assessment_repository.get_assessment = Mock(return_value=assessment)
    service._record_event = Mock()
    service.commit = Mock()

    result = service.add_feedback(
        "goal-1",
        "criterion-1",
        "assessment-1",
        "user-1",
        GoalAssessmentFeedbackType.CORRECTED,
        GoalCriterionResult.IN_PROGRESS,
        "  The evidence only shows partial rollout.  ",
    )

    assert result is assessment
    assert assessment.result == GoalCriterionResult.MET
    service._record_event.assert_called_once_with(
        "assessment-1",
        "CORRECTED",
        None,
        "user-1",
        {
            "corrected_result": "IN_PROGRESS",
            "comment": "The evidence only shows partial rollout.",
        },
    )
    service.commit.assert_called_once_with()


def test_batch_assessment_preserves_mixed_run_outcomes():
    first_goal = SimpleNamespace(id="goal-1", user_id="user-1")
    second_goal = SimpleNamespace(id="goal-2", user_id="user-1")
    run1 = SimpleNamespace(
        id="run-1",
        batch_id="batch-1",
        goal_id="goal-1",
        status=GoalAssessmentRunStatus.COMPLETED,
        trigger="ANALYZE_GOALS",
        started_at=None,
        finished_at=None,
        error_message=None,
    )
    run2 = SimpleNamespace(
        id="run-2",
        batch_id="batch-1",
        goal_id="goal-2",
        status=GoalAssessmentRunStatus.PARTIAL,
        trigger="ANALYZE_GOALS",
        started_at=None,
        finished_at=None,
        error_message="GitHub evidence refresh failed.",
    )

    class RunQuery:
        def __init__(self, run):
            self.run = run

        def filter(self, *_args):
            return self

        def order_by(self, *_args):
            return self

        def first(self):
            return self.run

    service = GoalAssessmentService(Mock())
    service.session.get.side_effect = [first_goal, second_goal]
    service.session.query.side_effect = [RunQuery(run1), RunQuery(run2)]
    service.assess_goal = AsyncMock(return_value=None)

    response = asyncio.run(service.assess_goals(["goal-1", "goal-2"], "user-1"))

    assert [run.status for run in response.runs] == [
        GoalAssessmentRunStatus.COMPLETED,
        GoalAssessmentRunStatus.PARTIAL,
    ]
    assert [run.error_message for run in response.runs] == [
        None,
        "GitHub evidence refresh failed.",
    ]
    assert response.runs[0].batch_id == response.runs[1].batch_id
    assert service.assess_goal.await_args_list[0].kwargs == {
        "batch_id": response.batch_id,
        "trigger": "ANALYZE_GOALS",
    }
    assert service.assess_goal.await_args_list[1].kwargs == {
        "batch_id": response.batch_id,
        "trigger": "ANALYZE_GOALS",
    }
