from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_v1_goals import (
    GoalCreateRequest,
    GoalDeactivateRequest,
    GoalReopenRequest,
    GoalRequirementsResponse,
    GoalResponse,
    GoalStatusHistoryResponse,
    GoalUpdateRequest,
    GoalValidationRunResponse,
)
from app.models.goal import GoalCreate, GoalStatus
from app.services.goal import GoalDeferralConflict, GoalDeletionConflict, GoalService
from app.services.goal_hierarchy import GoalHierarchyConflict, GoalHierarchyNotFound
from app.services.goal_validation import GoalSemanticValidationError
from app.services.goal_validation_runs import GoalValidationRunService

router = APIRouter(prefix="/goals", tags=["goals"])


def get_goal_service(db: Annotated[Session, Depends(get_db)]) -> GoalService:
    return GoalService(db)


def get_goal_validation_service(
    db: Annotated[Session, Depends(get_db)],
) -> GoalValidationRunService:
    return GoalValidationRunService(db)


def _to_response(goal) -> GoalResponse:
    return GoalResponse.model_validate(goal, from_attributes=True)


def _validation_to_response(run) -> GoalValidationRunResponse:
    return GoalValidationRunResponse(
        id=run.id,
        goal_id=run.goal_id,
        goal_version_id=run.goal_version_id,
        goal_version=run.goal_version.version,
        status=run.status,
        findings=run.findings,
        input_context=getattr(run, "input_context", None),
        result_context=getattr(run, "result_context", None),
        rule_set_version=run.rule_set_version,
        prompt_version=run.prompt_version,
        model_provider=run.model_provider,
        model_version=run.model_version,
        actor_user_id=run.actor_user_id,
        created_at=run.created_at,
    )


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
    try:
        goal_data = GoalCreate(
            user_id=user_id,
            title=request.title,
            description=request.description,
            scope=request.scope,
            goal_level=request.goal_level,
            start_date=request.start_date,
            end_date=request.end_date,
            status=GoalStatus.DRAFT,
            source=request.source,
            source_document_id=request.source_document_id,
            structured_fields=request.structured_fields,
        )
        goal = (
            service.create_goal(goal_data, parent_goal_id=request.parent_goal_id)
            if request.parent_goal_id is not None else service.create_goal(goal_data)
        )
    except GoalHierarchyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GoalHierarchyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
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
    try:
        updates = request.model_dump(exclude_unset=True)
        expected_deferrals = updates.pop("expected_deferred_requirements", None)
        if request.structured_fields is not None:
            updates["structured_fields"] = request.structured_fields.model_dump(
                mode="json", exclude_unset=True
            )
        kwargs = {"expected_deferred_requirements": expected_deferrals} if expected_deferrals is not None else {}
        goal = service.update_goal(goal_id, updates, changed_by_user_id=user_id, **kwargs)
    except GoalDeferralConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return _to_response(goal)


@router.post("/{goal_id}/approve", response_model=GoalResponse)
def approve_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    try:
        return _to_response(service.transition_status(goal_id, GoalStatus.APPROVED, changed_by_user_id=user_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{goal_id}/activate", response_model=GoalResponse)
def activate_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    try:
        return _to_response(service.transition_status(goal_id, GoalStatus.ACTIVE, changed_by_user_id=user_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{goal_id}/complete", response_model=GoalResponse)
def complete_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    try:
        return _to_response(service.transition_status(goal_id, GoalStatus.COMPLETED, changed_by_user_id=user_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{goal_id}/reopen", response_model=GoalResponse)
def reopen_goal(
    goal_id: str,
    request: GoalReopenRequest,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    try:
        return _to_response(
            service.transition_status(
                goal_id,
                GoalStatus.ACTIVE,
                reason=request.reason,
                changed_by_user_id=user_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{goal_id}/history", response_model=list[GoalStatusHistoryResponse])
def get_goal_status_history(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> list[GoalStatusHistoryResponse]:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    return [
        GoalStatusHistoryResponse.model_validate(item, from_attributes=True)
        for item in service.get_status_history(goal_id)
    ]


@router.post(
    "/{goal_id}/validate",
    response_model=GoalValidationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def validate_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    validation_service: Annotated[
        GoalValidationRunService,
        Depends(get_goal_validation_service),
    ],
) -> GoalValidationRunResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    try:
        run = await validation_service.validate_latest(goal_id, user_id)
    except GoalSemanticValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _validation_to_response(run)


@router.get(
    "/{goal_id}/validation-history",
    response_model=list[GoalValidationRunResponse],
)
def get_goal_validation_history(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    validation_service: Annotated[
        GoalValidationRunService,
        Depends(get_goal_validation_service),
    ],
) -> list[GoalValidationRunResponse]:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    return [
        _validation_to_response(run)
        for run in validation_service.get_history(goal_id)
    ]


@router.get("/{goal_id}/requirements", response_model=GoalRequirementsResponse)
def get_goal_requirements(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    validation_service: Annotated[GoalValidationRunService, Depends(get_goal_validation_service)],
) -> GoalRequirementsResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    try:
        return GoalRequirementsResponse.model_validate(validation_service.get_requirements(goal_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{goal_id}/deactivate", response_model=GoalResponse)
def deactivate_goal(
    goal_id: str,
    request: GoalDeactivateRequest,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> GoalResponse:
    _require_goal(service.get_goal_by_id(goal_id), user_id)
    try:
        return _to_response(
            service.transition_status(
                goal_id,
                GoalStatus.ARCHIVED,
                reason=request.reason,
                changed_by_user_id=user_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalService, Depends(get_goal_service)],
) -> None:
    goal = _require_goal(service.get_goal_by_id(goal_id), user_id)
    if goal.status != GoalStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only archived goals can be deleted",
        )
    try:
        service.delete_goal(goal_id)
    except GoalDeletionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
