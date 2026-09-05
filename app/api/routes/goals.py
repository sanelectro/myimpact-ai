from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.goal import Goal, GoalCreate
from app.services.goal import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])


def get_goal_service(
    db: Annotated[Session, Depends(get_db)],
) -> GoalService:
    return GoalService(db)


@router.post(
    "",
    response_model=Goal,
    status_code=status.HTTP_201_CREATED,
)
def create_goal(
    goal_data: GoalCreate,
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> Goal:
    goal = service.create_goal(goal_data)
    return Goal.model_validate(goal, from_attributes=True)


@router.get(
    "/user/{user_id}",
    response_model=list[Goal],
)
def get_goals_by_user_id(
    user_id: str,
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> list[Goal]:
    goals = service.get_goals_by_user_id(user_id)
    return [
        Goal.model_validate(goal, from_attributes=True)
        for goal in goals
    ]


@router.get(
    "/{goal_id}",
    response_model=Goal,
)
def get_goal_by_id(
    goal_id: str,
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> Goal:
    goal = service.get_goal_by_id(goal_id)

    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )

    return Goal.model_validate(goal, from_attributes=True)
