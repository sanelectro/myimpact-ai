from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.goal import GoalLevel, GoalStatus
from app.services.goal_hierarchy import (
    GoalHierarchyConflict,
    GoalHierarchyNotFound,
    GoalHierarchyService,
)

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalRelationshipChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class GoalParentChange(GoalRelationshipChange):
    parent_goal_id: str = Field(min_length=1, max_length=64)


class GoalRelationshipResponse(BaseModel):
    id: str
    parent_goal_id: str | None
    relationship_revision: int


class GoalHierarchySummary(GoalRelationshipResponse):
    title: str
    goal_level: GoalLevel | None
    status: GoalStatus


class GoalHierarchyResponse(BaseModel):
    goal: GoalHierarchySummary
    ancestors: list[GoalHierarchySummary]
    next_ancestor_id: str | None


class GoalRelationshipEventResponse(BaseModel):
    id: UUID
    goal_id: str
    old_parent_goal_id: str | None
    new_parent_goal_id: str | None
    actor_user_id: str
    reason: str | None
    relationship_revision: int
    created_at: datetime


def get_goal_hierarchy_service(db: Annotated[Session, Depends(get_db)]) -> GoalHierarchyService:
    return GoalHierarchyService(db)


def _http_error(exc: GoalHierarchyNotFound | GoalHierarchyConflict) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(exc, GoalHierarchyNotFound) else status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=str(exc))


@router.put("/{goal_id}/parent", response_model=GoalRelationshipResponse)
def set_goal_parent(
    goal_id: str,
    request: GoalParentChange,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalHierarchyService, Depends(get_goal_hierarchy_service)],
) -> GoalRelationshipResponse:
    try:
        goal = service.set_parent(goal_id, user_id, request.parent_goal_id, request.expected_revision, request.reason)
        return GoalRelationshipResponse.model_validate(goal, from_attributes=True)
    except (GoalHierarchyNotFound, GoalHierarchyConflict) as exc:
        raise _http_error(exc) from exc


@router.delete("/{goal_id}/parent", response_model=GoalRelationshipResponse)
def disconnect_goal_parent(
    goal_id: str,
    request: GoalRelationshipChange,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalHierarchyService, Depends(get_goal_hierarchy_service)],
) -> GoalRelationshipResponse:
    try:
        goal = service.set_parent(goal_id, user_id, None, request.expected_revision, request.reason)
        return GoalRelationshipResponse.model_validate(goal, from_attributes=True)
    except (GoalHierarchyNotFound, GoalHierarchyConflict) as exc:
        raise _http_error(exc) from exc


@router.get("/{goal_id}/hierarchy", response_model=GoalHierarchyResponse)
def get_goal_hierarchy(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalHierarchyService, Depends(get_goal_hierarchy_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> GoalHierarchyResponse:
    try:
        goal, ancestors, next_ancestor_id = service.hierarchy(goal_id, user_id, limit)
        return GoalHierarchyResponse(
            goal=GoalHierarchySummary.model_validate(goal, from_attributes=True),
            ancestors=[GoalHierarchySummary.model_validate(item, from_attributes=True) for item in ancestors],
            next_ancestor_id=next_ancestor_id,
        )
    except (GoalHierarchyNotFound, GoalHierarchyConflict) as exc:
        raise _http_error(exc) from exc


@router.get("/{goal_id}/children", response_model=list[GoalHierarchySummary])
def get_goal_children(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalHierarchyService, Depends(get_goal_hierarchy_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GoalHierarchySummary]:
    try:
        return [
            GoalHierarchySummary.model_validate(goal, from_attributes=True)
            for goal in service.children(goal_id, user_id, limit, offset)
        ]
    except GoalHierarchyNotFound as exc:
        raise _http_error(exc) from exc


@router.get("/{goal_id}/relationship-history", response_model=list[GoalRelationshipEventResponse])
def get_goal_relationship_history(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalHierarchyService, Depends(get_goal_hierarchy_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GoalRelationshipEventResponse]:
    try:
        return [
            GoalRelationshipEventResponse.model_validate(event)
            for event in service.history(goal_id, user_id, limit, offset)
        ]
    except GoalHierarchyNotFound as exc:
        raise _http_error(exc) from exc
