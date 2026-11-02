from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.threshold_governance import ThresholdSetDB
from app.db.session import get_db
from app.evaluation.evaluation_metrics import METRIC_DEFINITIONS
from app.models.threshold_governance import ThresholdDecision
from app.services.threshold_governance import (
    ThresholdValidationError,
    create_threshold_set,
    decide_threshold_set,
    propose_threshold_set,
)

router = APIRouter(prefix="/threshold-governance", tags=["m66-threshold-governance"])


class ThresholdItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str = Field(min_length=1, max_length=128)
    metric_definition_version: str = Field(min_length=1, max_length=100)
    operator: str = Field(min_length=2, max_length=2)
    threshold_value: float = Field(ge=0, le=1)
    unit: str = Field(min_length=1, max_length=32)
    rationale: str = Field(min_length=1, max_length=10000)
    required: bool = True


class ThresholdSetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    dataset_id: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=200)
    model_identifier: str = Field(min_length=1, max_length=200)
    model_configuration: dict = Field(default_factory=dict)
    evaluation_code_version: str = Field(min_length=1, max_length=200)
    proposal_rationale: str = Field(min_length=1, max_length=10000)
    items: list[ThresholdItemRequest] = Field(min_length=1, max_length=100)


class ThresholdDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ThresholdDecision
    rationale: str = Field(min_length=1, max_length=10000)
    policy_reference: str | None = Field(default=None, max_length=200)


def _require_platform_admin(user: AuthenticatedUser) -> None:
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )


def _threshold_response(threshold_set: ThresholdSetDB) -> dict[str, object]:
    return {
        "id": threshold_set.id,
        "version": threshold_set.version,
        "name": threshold_set.name,
        "status": threshold_set.status,
        "dataset_id": threshold_set.dataset_id,
        "dataset_version": threshold_set.dataset_version,
        "prompt_version": threshold_set.prompt_version,
        "model_identifier": threshold_set.model_identifier,
        "model_configuration": threshold_set.model_configuration,
        "evaluation_code_version": threshold_set.evaluation_code_version,
        "created_by_user_id": threshold_set.created_by_user_id,
        "created_at": threshold_set.created_at,
        "proposal_rationale": threshold_set.proposal_rationale,
        "items": [
            {
                "metric_id": item.metric_id,
                "metric_definition_version": item.metric_definition_version,
                "operator": item.operator,
                "threshold_value": float(item.threshold_value),
                "unit": item.unit,
                "rationale": item.rationale,
                "required": item.required,
            }
            for item in threshold_set.items
        ],
        "approvals": [
            {
                "decision": approval.decision,
                "approver_user_id": approval.approver_user_id,
                "decided_at": approval.decided_at,
                "rationale": approval.rationale,
                "policy_reference": approval.policy_reference,
            }
            for approval in threshold_set.approvals
        ],
    }


@router.get("/metric-definitions")
def list_metric_definitions(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> list[dict[str, object]]:
    _require_platform_admin(current_user)
    return [
        {
            "metric_id": definition.metric_id,
            "definition_version": definition.definition_version,
            "name": definition.name,
            "unit": definition.unit,
            "direction": definition.direction,
            "description": definition.description,
            "numerator_definition": definition.numerator_definition,
            "denominator_definition": definition.denominator_definition,
            "zero_denominator_behavior": definition.zero_denominator_behavior,
            "inclusion_rules": definition.inclusion_rules,
            "exclusion_rules": definition.exclusion_rules,
            "required_inputs": definition.required_inputs,
            "limitations": definition.limitations,
            "calculation_version": definition.calculation_version,
        }
        for definition in METRIC_DEFINITIONS
    ]


@router.get("/threshold-sets")
def list_threshold_sets(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, object]]:
    _require_platform_admin(current_user)
    threshold_sets = db.scalars(
        select(ThresholdSetDB).order_by(ThresholdSetDB.created_at.desc())
    ).all()
    return [_threshold_response(threshold_set) for threshold_set in threshold_sets]


@router.post(
    "/threshold-sets",
    status_code=status.HTTP_201_CREATED,
)
def create_threshold_set_route(
    request: ThresholdSetCreateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _require_platform_admin(current_user)
    try:
        threshold_set = create_threshold_set(
            db,
            name=request.name,
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            prompt_version=request.prompt_version,
            model_identifier=request.model_identifier,
            model_configuration=request.model_configuration,
            evaluation_code_version=request.evaluation_code_version,
            created_by_user_id=current_user.user_id,
            proposal_rationale=request.proposal_rationale,
            items=[item.model_dump() for item in request.items],
        )
    except ThresholdValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _threshold_response(threshold_set)


@router.post("/threshold-sets/{threshold_set_id}/propose")
def propose_threshold_set_route(
    threshold_set_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _require_platform_admin(current_user)
    try:
        threshold_set = propose_threshold_set(
            db,
            threshold_set_id=threshold_set_id,
            actor_user_id=current_user.user_id,
        )
    except ThresholdValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _threshold_response(threshold_set)


@router.post("/threshold-sets/{threshold_set_id}/decision")
def decide_threshold_set_route(
    threshold_set_id: str,
    request: ThresholdDecisionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _require_platform_admin(current_user)
    try:
        approval = decide_threshold_set(
            db,
            threshold_set_id=threshold_set_id,
            approver_user_id=current_user.user_id,
            decision=request.decision,
            rationale=request.rationale,
            authorized=True,
            policy_reference=request.policy_reference,
        )
    except ThresholdValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": approval.id,
        "threshold_set_id": approval.threshold_set_id,
        "decision": approval.decision,
        "approver_user_id": approval.approver_user_id,
        "decided_at": approval.decided_at,
        "rationale": approval.rationale,
        "policy_reference": approval.policy_reference,
    }
