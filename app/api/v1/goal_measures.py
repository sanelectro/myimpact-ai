from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.goal_assessment import get_assessment_service
from app.api.v1.goals import _require_goal, get_goal_service
from app.db.models.goal import GoalDB
from app.db.session import get_db
from app.models.goal import GoalStatus
from app.models.goal_criteria import GoalAssessmentSummaryResponse
from app.services.goal import GoalService
from app.services.goal_assessment import GoalAssessmentService

router = APIRouter(prefix="/goals", tags=["goal-measures"])


class ChildExecutionCounts(BaseModel):
    total: int
    by_status: dict[GoalStatus, int]


class GoalMeasuresResponse(BaseModel):
    goal_id: str
    child_execution: ChildExecutionCounts
    own_criterion_assessment: GoalAssessmentSummaryResponse | None
    outcome_achievement: None = None
    demonstrated_impact: None = None


@router.get("/{goal_id}/measures", response_model=GoalMeasuresResponse)
def get_goal_measures(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    assessment_service: Annotated[GoalAssessmentService, Depends(get_assessment_service)],
    db: Annotated[Session, Depends(get_db)],
    include_assessment: bool = True,
) -> GoalMeasuresResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    rows = db.execute(
        select(GoalDB.status, func.count(GoalDB.id))
        .where(GoalDB.parent_goal_id == goal_id, GoalDB.user_id == user_id)
        .group_by(GoalDB.status)
    ).all()
    counts = {status: count for status, count in rows}
    return GoalMeasuresResponse(
        goal_id=goal_id,
        child_execution=ChildExecutionCounts(total=sum(counts.values()), by_status=counts),
        own_criterion_assessment=assessment_service.get_summary(goal_id) if include_assessment else None,
    )
