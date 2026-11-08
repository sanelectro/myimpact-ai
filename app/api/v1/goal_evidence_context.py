from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.api.v1.evidence import (
    _require_goal,
    get_evidence_mapping_service,
    get_evidence_service,
    get_goal_service,
)
from app.db.session import get_db
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.models.evidence import EvidenceStatus
from app.models.evidence_approval import EvidenceApprovalStatus
from app.models.evidence_mapping import EvidenceMappingKind, EvidenceRelevance
from app.services.evidence import EvidenceService
from app.services.evidence_mapping import EvidenceMappingService
from app.services.goal import GoalService
from app.services.goal_evidence_context import GoalEvidenceContextService
from app.services.goal_hierarchy import GoalHierarchyNotFound

router = APIRouter(prefix="/goals", tags=["goal-evidence"])


class EvidenceLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=64)
    mapping_kind: EvidenceMappingKind = EvidenceMappingKind.PRIMARY
    contribution_description: str | None = Field(default=None, max_length=4000)
    relevance: EvidenceRelevance

    @field_validator("contribution_description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def validate_description(self):
        if self.mapping_kind is EvidenceMappingKind.PRIMARY and self.contribution_description:
            raise ValueError("A contribution description requires a contribution mapping")
        return self


class EvidenceLinkResponse(BaseModel):
    mapping_id: str
    evidence_id: str
    goal_id: str
    mapping_kind: EvidenceMappingKind
    contribution_description: str | None
    approval_status: str


class EvidenceOriginResponse(BaseModel):
    origin: str
    source_goal_id: str
    goal_path: list[str]
    mapping_id: str
    mapping_kind: EvidenceMappingKind
    contribution_description: str | None
    relevance: EvidenceRelevance
    confidence: float
    approval_status: str | None


class EvidenceContextItemResponse(BaseModel):
    evidence_id: str
    title: str
    description: str | None
    source_type: str
    source_url: str | None
    captured_at: datetime
    source_updated_at: datetime | None
    origins: list[EvidenceOriginResponse]


class EvidenceContextResponse(BaseModel):
    items: list[EvidenceContextItemResponse]
    has_more: bool
    next_offset: int | None
    hierarchy_truncated: bool


def get_goal_evidence_context_service(
    db: Annotated[Session, Depends(get_db)],
) -> GoalEvidenceContextService:
    return GoalEvidenceContextService(db)


@router.post("/{goal_id}/evidence-links", response_model=EvidenceLinkResponse, status_code=201)
def link_existing_evidence(
    goal_id: str,
    request: EvidenceLinkRequest,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    evidence_service: Annotated[EvidenceService, Depends(get_evidence_service)],
    mapping_service: Annotated[EvidenceMappingService, Depends(get_evidence_mapping_service)],
) -> EvidenceLinkResponse:
    goal = _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    if not goal_service.is_evidence_submission_eligible(goal):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evidence submission requires an eligible goal.",
        )
    evidence = evidence_service.get_evidence_by_id(request.evidence_id)
    if evidence is None or evidence.user_id != user_id or evidence.status != EvidenceStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    try:
        mapping = mapping_service.create_mapping(
            evidence_id=evidence.id,
            goal_id=goal_id,
            relevance=request.relevance,
            confidence=1.0,
            reason="Linked by the goal owner.",
            mapping_kind=request.mapping_kind,
            contribution_description=request.contribution_description,
            created_by_user_id=user_id,
        )
    except EvidenceMappingAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EvidenceLinkResponse(
        mapping_id=mapping.id,
        evidence_id=evidence.id,
        goal_id=goal_id,
        mapping_kind=mapping.mapping_kind,
        contribution_description=mapping.contribution_description,
        approval_status=EvidenceApprovalStatus.PENDING.value,
    )


@router.get("/{goal_id}/evidence-context", response_model=EvidenceContextResponse)
def get_goal_evidence_context(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalEvidenceContextService, Depends(get_goal_evidence_context_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    max_depth: Annotated[int, Query(ge=0, le=100)] = 20,
) -> EvidenceContextResponse:
    try:
        return EvidenceContextResponse.model_validate(
            service.get_context(goal_id, user_id, limit=limit, offset=offset, max_depth=max_depth)
        )
    except GoalHierarchyNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
