from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_v1_goals import GoalAssessmentResponse
from app.services.goal import GoalService
from app.services.goal_assessment import GoalAssessmentService

router = APIRouter(prefix="/goals", tags=["goal-assessment"])


def get_goal_service(db: Annotated[Session, Depends(get_db)]) -> GoalService:
    return GoalService(db)


def get_goal_assessment_service(
    db: Annotated[Session, Depends(get_db)],
) -> GoalAssessmentService:
    return GoalAssessmentService(db)


def _require_goal(goal, user_id: str):
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.get("/{goal_id}/assessment", response_model=GoalAssessmentResponse)
def get_goal_assessment(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    assessment_service: Annotated[GoalAssessmentService, Depends(get_goal_assessment_service)],
) -> GoalAssessmentResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    return assessment_service.assess(goal_id)
