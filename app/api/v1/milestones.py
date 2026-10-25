from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.goals import _require_goal, get_goal_service
from app.db.session import get_db
from app.exceptions import MilestoneSuggestionError
from app.models.goal import Goal
from app.models.milestone import (
    MilestoneCreate,
    MilestoneResponse,
    MilestoneSuggestion,
    MilestoneUpdate,
)
from app.services.goal import GoalService
from app.services.knowledge.milestone_suggestion import MilestoneSuggestionService
from app.services.llm.factory import create_llm_service
from app.services.milestone import MilestoneService

router = APIRouter(prefix="/goals/{goal_id}/milestones", tags=["milestones"])


def get_milestone_service(db: Annotated[Session, Depends(get_db)]) -> MilestoneService:
    return MilestoneService(db)


def get_milestone_suggestion_service() -> MilestoneSuggestionService:
    return MilestoneSuggestionService(create_llm_service())


def _require_owned_goal(goal_id: str, user_id: str, service: GoalService) -> None:
    _require_goal(service.get_goal_by_id(goal_id), user_id)


@router.get("", response_model=list[MilestoneResponse])
def list_milestones(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[MilestoneService, Depends(get_milestone_service)],
) -> list[MilestoneResponse]:
    _require_owned_goal(goal_id, user_id, goal_service)
    return [
        MilestoneResponse.model_validate(item, from_attributes=True)
        for item in service.get_milestones_by_goal_id(goal_id)
    ]


@router.post("/suggestions", response_model=list[MilestoneSuggestion])
async def suggest_milestones(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    suggestion_service: Annotated[
        MilestoneSuggestionService,
        Depends(get_milestone_suggestion_service),
    ],
) -> list[MilestoneSuggestion]:
    goal_db = _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    goal = Goal.model_validate(goal_db, from_attributes=True)
    try:
        return await suggestion_service.suggest(goal)
    except MilestoneSuggestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
def create_milestone(
    goal_id: str,
    request: MilestoneCreate,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[MilestoneService, Depends(get_milestone_service)],
) -> MilestoneResponse:
    _require_owned_goal(goal_id, user_id, goal_service)
    milestone = service.create_milestone(goal_id, request)
    return MilestoneResponse.model_validate(milestone, from_attributes=True)


@router.put("/{milestone_id}", response_model=MilestoneResponse)
def update_milestone(
    goal_id: str,
    milestone_id: str,
    request: MilestoneUpdate,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[MilestoneService, Depends(get_milestone_service)],
) -> MilestoneResponse:
    _require_owned_goal(goal_id, user_id, goal_service)
    if not request.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one milestone field must be provided",
        )
    try:
        milestone = service.update_milestone(
            goal_id,
            milestone_id,
            request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MilestoneResponse.model_validate(milestone, from_attributes=True)


@router.post("/{milestone_id}/archive", response_model=MilestoneResponse)
def archive_milestone(
    goal_id: str,
    milestone_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[MilestoneService, Depends(get_milestone_service)],
) -> MilestoneResponse:
    _require_owned_goal(goal_id, user_id, goal_service)
    try:
        milestone = service.archive_milestone(goal_id, milestone_id)
    except ValueError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if "already archived" in str(exc)
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return MilestoneResponse.model_validate(milestone, from_attributes=True)


@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_milestone(
    goal_id: str,
    milestone_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[MilestoneService, Depends(get_milestone_service)],
) -> None:
    _require_owned_goal(goal_id, user_id, goal_service)
    try:
        service.delete_archived_milestone(goal_id, milestone_id)
    except ValueError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if "Only archived" in str(exc)
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
