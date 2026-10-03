from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_v1_goals import GoalCreateRequest, GoalResponse, GoalUpdateRequest
from app.models.goal import GoalCreate
from app.services.goal import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])


def get_goal_service(db: Annotated[Session, Depends(get_db)]) -> GoalService:
    return GoalService(db)


def _to_response(goal) -> GoalResponse:
    return GoalResponse.model_validate(goal, from_attributes=True)


def _require_goal(goal, user_id: str):
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.post("", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    request: GoalCreateRequest,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    goal = service.create_goal(
        GoalCreate(
            user_id=user_id,
            title=request.title,
            description=request.description,
            start_date=request.start_date,
            end_date=request.end_date,
            status=request.status,
            source=request.source,
        )
    )
    return _to_response(goal)


@router.get("", response_model=list[GoalResponse])
def list_goals(
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> list[GoalResponse]:
    return [_to_response(goal) for goal in service.get_goals_by_user_id(user_id)]


@router.get("/{goal_id}", response_model=GoalResponse)
def get_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    return _to_response(_require_goal(service.get_goal_by_id(goal_id), user_id))


@router.put("/{goal_id}", response_model=GoalResponse)
def update_goal(
    goal_id: str,
    request: GoalUpdateRequest,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    goal = service.update_goal(goal_id, request.model_dump(exclude_unset=True))
    return _to_response(goal)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> None:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    service.delete_goal(goal_id)
