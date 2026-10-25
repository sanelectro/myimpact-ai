from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.v1.goal_assessment import get_assessment_execution_service
from app.api.v1.goal_criteria import (
    get_criteria_generation_service,
)
from app.api.v1.goals import get_goal_service
from app.main import app
from app.models.goal_criteria import (
    GoalAssessmentBatchResponse,
    GoalAssessmentRunResponse,
    GoalAssessmentRunStatus,
    GoalAssessmentSummaryResponse,
    GoalCriterionApprovalStatus,
    GoalCriterionDefinition,
    GoalCriterionResponse,
    GoalCriterionType,
    GoalCriterionVersionResponse,
)


class AssessmentServiceStub:
    async def assess_goals(self, goal_ids, user_id):
        assert goal_ids == ["goal-1"]
        assert user_id == "user-1"
        return GoalAssessmentBatchResponse(batch_id="batch-1", runs=[])


def test_batch_assessment_returns_success_after_synchronous_execution():
    previous = app.dependency_overrides.get(get_assessment_execution_service)
    app.dependency_overrides[get_assessment_execution_service] = (
        lambda: AssessmentServiceStub()
    )
    try:
        response = TestClient(app).post(
            "/api/v1/goals/assessment-runs",
            params={"user_id": "user-1"},
            json={"goal_ids": ["goal-1"]},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_assessment_execution_service, None)
        else:
            app.dependency_overrides[get_assessment_execution_service] = previous

    assert response.status_code == 200
    assert response.json() == {"batch_id": "batch-1", "runs": []}


def test_batch_assessment_rejects_duplicate_goal_ids():
    response = TestClient(app).post(
        "/api/v1/goals/assessment-runs",
        params={"user_id": "user-1"},
        json={"goal_ids": ["goal-1", "goal-1"]},
    )

    assert response.status_code == 422


def test_batch_assessment_returns_mixed_per_goal_outcomes():
    class MixedAssessmentServiceStub:
        async def assess_goals(self, goal_ids, user_id):
            assert goal_ids == ["goal-1", "goal-2"]
            assert user_id == "user-1"
            return GoalAssessmentBatchResponse(
                batch_id="batch-mixed",
                runs=[
                    GoalAssessmentRunResponse(
                        id="run-completed",
                        batch_id="batch-mixed",
                        goal_id="goal-1",
                        status=GoalAssessmentRunStatus.COMPLETED,
                        trigger="ANALYZE_GOALS",
                        started_at=None,
                        finished_at=None,
                        error_message=None,
                    ),
                    GoalAssessmentRunResponse(
                        id="run-partial",
                        batch_id="batch-mixed",
                        goal_id="goal-2",
                        status=GoalAssessmentRunStatus.PARTIAL,
                        trigger="ANALYZE_GOALS",
                        started_at=None,
                        finished_at=None,
                        error_message="GitHub evidence refresh failed.",
                    ),
                ],
            )

    previous = app.dependency_overrides.get(get_assessment_execution_service)
    app.dependency_overrides[get_assessment_execution_service] = (
        lambda: MixedAssessmentServiceStub()
    )
    try:
        response = TestClient(app).post(
            "/api/v1/goals/assessment-runs",
            params={"user_id": "user-1"},
            json={"goal_ids": ["goal-1", "goal-2"]},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_assessment_execution_service, None)
        else:
            app.dependency_overrides[get_assessment_execution_service] = previous

    assert response.status_code == 200
    assert [run["status"] for run in response.json()["runs"]] == [
        "COMPLETED",
        "PARTIAL",
    ]
    assert response.json()["runs"][1]["error_message"] == "GitHub evidence refresh failed."


def test_feedback_route_rejects_a_correction_without_an_assessed_result():
    response = TestClient(app).post(
        "/api/v1/goals/goal-1/criteria/criterion-1/assessments/assessment-1/feedback",
        params={"user_id": "user-1"},
        json={"feedback_type": "CORRECTED"},
    )

    assert response.status_code == 422


def test_reanalysis_route_returns_partial_source_failure_details():
    class GoalServiceStub:
        def get_goal_by_id(self, goal_id):
            return SimpleNamespace(id=goal_id, user_id="user-1")

    class AssessmentServiceStub:
        async def assess_goal(self, goal_id, user_id):
            assert goal_id == "goal-1"
            assert user_id == "user-1"
            return GoalAssessmentSummaryResponse(
                goal_id=goal_id,
                run_id="run-1",
                run_status=GoalAssessmentRunStatus.PARTIAL,
                run_error_message="Jira evidence refresh failed.",
                criteria_count=0,
                assessed_criteria_count=0,
                criteria_met_count=0,
                criteria_met_percentage=None,
                goal_progress_percentage=None,
                evidence_coverage_percentage=None,
                average_confidence=None,
                criteria=[],
                updated_at=None,
            )

    overrides = {
        get_goal_service: lambda: GoalServiceStub(),
        get_assessment_execution_service: lambda: AssessmentServiceStub(),
    }
    previous = {
        dependency: app.dependency_overrides.get(dependency)
        for dependency in overrides
    }
    app.dependency_overrides.update(overrides)
    try:
        response = TestClient(app).post(
            "/api/v1/goals/goal-1/assessment/reanalyze",
            params={"user_id": "user-1"},
        )
    finally:
        for dependency, original in previous.items():
            if original is None:
                app.dependency_overrides.pop(dependency, None)
            else:
                app.dependency_overrides[dependency] = original

    assert response.status_code == 200
    assert response.json()["run_status"] == "PARTIAL"
    assert response.json()["run_error_message"] == "Jira evidence refresh failed."


def test_reanalysis_route_rejects_goals_owned_by_another_user():
    class GoalServiceStub:
        def get_goal_by_id(self, goal_id):
            return SimpleNamespace(id=goal_id, user_id="another-user")

    class AssessmentServiceStub:
        async def assess_goal(self, _goal_id, _user_id):
            raise AssertionError("Assessment must not run for another user's goal.")

    overrides = {
        get_goal_service: lambda: GoalServiceStub(),
        get_assessment_execution_service: lambda: AssessmentServiceStub(),
    }
    previous = {
        dependency: app.dependency_overrides.get(dependency)
        for dependency in overrides
    }
    app.dependency_overrides.update(overrides)
    try:
        response = TestClient(app).post(
            "/api/v1/goals/goal-1/assessment/reanalyze",
            params={"user_id": "user-1"},
        )
    finally:
        for dependency, original in previous.items():
            if original is None:
                app.dependency_overrides.pop(dependency, None)
            else:
                app.dependency_overrides[dependency] = original
    assert response.status_code == 404
    assert response.status_code == 404


def test_generate_criteria_route_returns_unapproved_proposals():
    now = datetime.now(UTC)
    criterion = GoalCriterionResponse(
        id="criterion-1",
        goal_id="goal-1",
        current_version=None,
        is_retired=False,
        created_at=now,
        updated_at=now,
        versions=[
            GoalCriterionVersionResponse(
                id="version-1",
                criterion_id="criterion-1",
                version=1,
                definition=GoalCriterionDefinition(
                    criterion_type=GoalCriterionType.BINARY,
                    description="Enable canary validation",
                    completion_conditions="Canary validation is enabled in production.",
                ),
                approval_status=GoalCriterionApprovalStatus.PROPOSED,
                created_by_user_id="user-1",
                prompt_version="m66-criteria-v1",
                model_version="synthetic-test-model",
                created_at=now,
                approved_by_user_id=None,
                approved_at=None,
            )
        ],
    )

    class GoalServiceStub:
        def get_goal_by_id(self, goal_id):
            return SimpleNamespace(id=goal_id, user_id="user-1")

    class CriteriaServiceStub:
        async def generate(self, goal, user_id):
            assert goal.id == "goal-1"
            assert user_id == "user-1"
            return [criterion]

    overrides = {
        get_goal_service: lambda: GoalServiceStub(),
        get_criteria_generation_service: lambda: CriteriaServiceStub(),
    }
    previous = {dependency: app.dependency_overrides.get(dependency) for dependency in overrides}
    app.dependency_overrides.update(overrides)
    try:
        response = TestClient(app).post(
            "/api/v1/goals/goal-1/criteria/generate",
            params={"user_id": "user-1"},
        )
    finally:
        for dependency, original in previous.items():
            if original is None:
                app.dependency_overrides.pop(dependency, None)
            else:
                app.dependency_overrides[dependency] = original

    assert response.status_code == 201
    proposal = response.json()[0]
    assert proposal["current_version"] is None
    assert proposal["versions"][0]["approval_status"] == "PROPOSED"
    assert proposal["versions"][0]["definition"]["description"] == "Enable canary validation"
