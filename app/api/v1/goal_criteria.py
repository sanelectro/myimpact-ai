from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.goals import _require_goal, get_goal_service
from app.db.session import get_db
from app.exceptions import GoalCriteriaGenerationError
from app.models.goal_criteria import (
    GoalCriterionCreateRequest,
    GoalCriterionResponse,
    GoalCriterionUpdateRequest,
)
from app.services.goal import GoalService
from app.services.goal_criteria import GoalCriteriaService
from app.services.llm.factory import create_llm_service

router = APIRouter(prefix="/goals/{goal_id}/criteria", tags=["goal-criteria"])


def get_criteria_service(db: Annotated[Session, Depends(get_db)]) -> GoalCriteriaService:
    return GoalCriteriaService(db)


def get_criteria_generation_service(
    db: Annotated[Session, Depends(get_db)],
) -> GoalCriteriaService:
    return GoalCriteriaService(db, create_llm_service())


def _owned_goal(goal_id: str, user_id: str, service: GoalService):
    return _require_goal(service.get_goal_by_id(goal_id), user_id)


@router.get("", response_model=list[GoalCriterionResponse])
def list_goal_criteria(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[GoalCriteriaService, Depends(get_criteria_service)],
) -> list[GoalCriterionResponse]:
    _owned_goal(goal_id, user_id, goal_service)
    return [
        GoalCriterionResponse.model_validate(criterion, from_attributes=True)
        for criterion in service.list_for_goal(goal_id)
    ]


@router.post(
    "/generate",
    response_model=list[GoalCriterionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_goal_criteria(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[
        GoalCriteriaService,
        Depends(get_criteria_generation_service),
    ],
) -> list[GoalCriterionResponse]:
    goal = _owned_goal(goal_id, user_id, goal_service)
    try:
        criteria = await service.generate(goal, user_id)
    except GoalCriteriaGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return [
        GoalCriterionResponse.model_validate(criterion, from_attributes=True)
        for criterion in criteria
    ]


@router.post(
    "",
    response_model=GoalCriterionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_goal_criterion(
    goal_id: str,
    request: GoalCriterionCreateRequest,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[GoalCriteriaService, Depends(get_criteria_service)],
) -> GoalCriterionResponse:
    _owned_goal(goal_id, user_id, goal_service)
    criterion = service.create_manual(goal_id, user_id, request)
    return GoalCriterionResponse.model_validate(criterion, from_attributes=True)


@router.put("/{criterion_id}", response_model=GoalCriterionResponse)
def update_goal_criterion(
    goal_id: str,
    criterion_id: str,
    request: GoalCriterionUpdateRequest,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[GoalCriteriaService, Depends(get_criteria_service)],
) -> GoalCriterionResponse:
    _owned_goal(goal_id, user_id, goal_service)
    try:
        criterion, _ = service.add_version(
            goal_id,
            criterion_id,
            user_id,
            request,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return GoalCriterionResponse.model_validate(criterion, from_attributes=True)


@router.post(
    "/{criterion_id}/versions/{version_id}/approve",
    response_model=GoalCriterionResponse,
)
def approve_goal_criterion_version(
    goal_id: str,
    criterion_id: str,
    version_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[GoalCriteriaService, Depends(get_criteria_service)],
) -> GoalCriterionResponse:
    _owned_goal(goal_id, user_id, goal_service)
    try:
        criterion = service.approve_version(
            goal_id,
            criterion_id,
            version_id,
            user_id,
        )
    except ValueError as exc:
        code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(exc).casefold()
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return GoalCriterionResponse.model_validate(criterion, from_attributes=True)


@router.delete(
    "/{criterion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def retire_goal_criterion(
    goal_id: str,
    criterion_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    service: Annotated[GoalCriteriaService, Depends(get_criteria_service)],
) -> None:
    _owned_goal(goal_id, user_id, goal_service)
    try:
        service.retire(goal_id, criterion_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
