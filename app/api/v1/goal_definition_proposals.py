from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.goal_definition_proposal import GoalDefinitionProposalHeadDB
from app.db.session import get_db
from app.models.goal import GoalStatus
from app.repositories.goal import GoalRepository
from app.repositories.goal_validation import GoalValidationRepository
from app.services.goal_baseline_observations import GoalBaselineConflict
from app.services.goal_definition_proposals import (
    GoalDefinitionProposalService,
    GoalProposalChanges,
    GoalProposalConflict,
)
from app.services.goal_hierarchy import GoalHierarchyConflict, GoalHierarchyNotFound
from app.services.goal_proposal_previews import GoalProposalPreviewService
from app.services.goal_validation import GoalSemanticValidationError
from app.services.goal_validation_runs import GoalValidationRunService

router = APIRouter(prefix="/goals", tags=["goal-definition-proposals"])


class PrepareGoalProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_base_version_id: str | None = Field(default=None, min_length=1, max_length=64)
    expected_source_version_id: str | None = Field(default=None, min_length=1, max_length=64)
    expected_proposal_revision: int = Field(ge=0)
    expected_relationship_revision: int = Field(ge=0)
    changes: GoalProposalChanges

    @model_validator(mode="after")
    def require_one_baseline(self):
        if (self.expected_base_version_id is None) == (self.expected_source_version_id is None):
            raise ValueError("Provide either an operative baseline or an observation source")
        return self


class GoalProposalVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_version_id: str = Field(min_length=1, max_length=64)


class GoalProposalResultResponse(BaseModel):
    goal_id: str
    version_id: str
    revision: int
    outcome: str


class GoalProposalSnapshotResponse(BaseModel):
    version_id: str
    revision: int
    content: dict[str, Any]
    latest_validation_id: str | None = None
    latest_validation_status: str | None = None


class GoalProposalStateResponse(BaseModel):
    goal_id: str
    relationship_revision: int
    operative_version_id: str | None
    latest_standard_version_id: str
    proposal: GoalProposalSnapshotResponse | None


class GoalProposalValidationResponse(BaseModel):
    id: str
    goal_version_id: str
    status: str
    findings: list[dict[str, Any]]


class GoalDateConflictResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    parent_goal_id: str
    child_goal_id: str
    child_field: str
    child_date: date
    parent_field: str
    parent_date: date


class GoalProposalPreviewResponse(BaseModel):
    goal_id: str
    proposal_version_id: str
    conflicts: list[GoalDateConflictResponse]


def _owned_goal(db: Session, goal_id: str, user_id: str):
    goal = GoalRepository(db).get_by_id(goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return goal


@router.get("/{goal_id}/definition-proposal", response_model=GoalProposalStateResponse)
def get_goal_proposal(
    goal_id: str,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GoalProposalStateResponse:
    goal = _owned_goal(db, goal_id, user.user_id)
    if goal.status not in {GoalStatus.APPROVED, GoalStatus.ACTIVE}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only ongoing goals can be revised")
    latest = GoalRepository(db).get_latest_version(goal_id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Goal baseline is unavailable")
    head = db.get(GoalDefinitionProposalHeadDB, goal_id)
    proposal = None
    if head is not None:
        try:
            version = GoalDefinitionProposalService(db).require_prepared_proposal(
                goal_id, head.proposal_version_id, user.user_id
            )
        except GoalProposalConflict as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        run = GoalValidationRepository(db).get_latest_for_version(goal_id, version.id)
        proposal = GoalProposalSnapshotResponse(
            version_id=version.id, revision=head.revision, content=version.content,
            latest_validation_id=run.id if run else None,
            latest_validation_status=run.status if run else None,
        )
    return GoalProposalStateResponse(
        goal_id=goal_id, relationship_revision=goal.relationship_revision,
        operative_version_id=goal.operative_goal_version_id,
        latest_standard_version_id=latest.id, proposal=proposal,
    )


@router.post("/{goal_id}/definition-proposal", response_model=GoalProposalResultResponse)
def prepare_goal_proposal(
    goal_id: str,
    request: PrepareGoalProposalRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GoalProposalResultResponse:
    _owned_goal(db, goal_id, user.user_id)
    service = GoalDefinitionProposalService(db)
    arguments = {
        "goal_id": goal_id, "actor_user_id": user.user_id,
        "idempotency_key": request.idempotency_key,
        "expected_proposal_revision": request.expected_proposal_revision,
        "expected_relationship_revision": request.expected_relationship_revision,
        "changes": request.changes,
    }
    try:
        if request.expected_base_version_id is not None:
            result = service.stage_proposal(
                **arguments, expected_base_version_id=request.expected_base_version_id
            )
        elif request.expected_source_version_id is not None:
            result = service.stage_observed_proposal(
                **arguments, expected_source_version_id=request.expected_source_version_id
            )
        else:
            raise RuntimeError("Validated proposal request has no baseline")
        db.commit()
    except (GoalProposalConflict, GoalBaselineConflict) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return GoalProposalResultResponse.model_validate(result, from_attributes=True)


@router.post(
    "/{goal_id}/definition-proposal/validate",
    response_model=GoalProposalValidationResponse,
)
async def validate_goal_proposal(
    goal_id: str,
    request: GoalProposalVersionRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GoalProposalValidationResponse:
    _owned_goal(db, goal_id, user.user_id)
    try:
        run = await GoalValidationRunService(db).validate_prepared_proposal(
            goal_id, request.proposal_version_id, user.user_id
        )
    except GoalSemanticValidationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return GoalProposalValidationResponse.model_validate(run, from_attributes=True)


@router.post("/{goal_id}/definition-proposal/date-preview", response_model=GoalProposalPreviewResponse)
def preview_goal_proposal_dates(
    goal_id: str,
    request: GoalProposalVersionRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GoalProposalPreviewResponse:
    _owned_goal(db, goal_id, user.user_id)
    try:
        preview = GoalProposalPreviewService(db).preview_dates(
            goal_id, request.proposal_version_id, user.user_id
        )
    except (GoalProposalConflict, GoalHierarchyConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GoalHierarchyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return GoalProposalPreviewResponse(
        goal_id=preview.goal_id, proposal_version_id=preview.proposal_version_id,
        conflicts=[GoalDateConflictResponse.model_validate(item) for item in preview.conflicts],
    )
