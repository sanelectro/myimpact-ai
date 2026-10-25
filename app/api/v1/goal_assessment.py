from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.goals import _require_goal, get_goal_service
from app.db.models.goal_criterion import GoalAssessmentRunDB
from app.db.session import get_db
from app.models.goal_criteria import (
    GoalAssessmentBatchRequest,
    GoalAssessmentBatchResponse,
    GoalAssessmentFeedbackRequest,
    GoalAssessmentRunResponse,
    GoalAssessmentSummaryResponse,
)
from app.services.goal import GoalService
from app.services.goal_assessment import GoalAssessmentService
from app.services.llm.factory import create_llm_service

router = APIRouter(prefix="/goals", tags=["goal-assessment"])


def get_assessment_service(
    db: Annotated[Session, Depends(get_db)],
) -> GoalAssessmentService:
    return GoalAssessmentService(db)


def get_assessment_execution_service(
    db: Annotated[Session, Depends(get_db)],
) -> GoalAssessmentService:
    return GoalAssessmentService(db, create_llm_service())


@router.get(
    "/{goal_id}/assessment",
    response_model=GoalAssessmentSummaryResponse,
)
def get_goal_assessment(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    assessment_service: Annotated[
        GoalAssessmentService,
        Depends(get_assessment_service),
    ],
) -> GoalAssessmentSummaryResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    return assessment_service.get_summary(goal_id)


@router.post(
    "/{goal_id}/assessment/reanalyze",
    response_model=GoalAssessmentSummaryResponse,
)
async def reanalyze_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    assessment_service: Annotated[
        GoalAssessmentService,
        Depends(get_assessment_execution_service),
    ],
) -> GoalAssessmentSummaryResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    try:
        return await assessment_service.assess_goal(goal_id, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/assessment-runs",
    response_model=GoalAssessmentBatchResponse,
)
async def analyze_goals(
    request: GoalAssessmentBatchRequest,
    user_id: Annotated[str, Query(min_length=1)],
    assessment_service: Annotated[
        GoalAssessmentService,
        Depends(get_assessment_execution_service),
    ],
) -> GoalAssessmentBatchResponse:
    try:
        return await assessment_service.assess_goals(request.goal_ids, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/assessment-runs/{run_id}",
    response_model=GoalAssessmentRunResponse,
)
def get_assessment_run(
    run_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    db: Annotated[Session, Depends(get_db)],
) -> GoalAssessmentRunResponse:
    run = db.get(GoalAssessmentRunDB, run_id)
    if run is None or run.goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment run not found",
        )
    return GoalAssessmentRunResponse.model_validate(run, from_attributes=True)


@router.post(
    "/{goal_id}/criteria/{criterion_id}/assessments/{assessment_id}/feedback",
    response_model=GoalAssessmentSummaryResponse,
)
def submit_assessment_feedback(
    goal_id: str,
    criterion_id: str,
    assessment_id: str,
    request: GoalAssessmentFeedbackRequest,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    assessment_service: Annotated[
        GoalAssessmentService,
        Depends(get_assessment_service),
    ],
) -> GoalAssessmentSummaryResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    try:
        assessment_service.add_feedback(
            goal_id,
            criterion_id,
            assessment_id,
            user_id,
            request.feedback_type,
            request.corrected_result,
            request.comment,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return assessment_service.get_summary(goal_id)
