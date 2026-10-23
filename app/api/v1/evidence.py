from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_v1_impact import GoalEvidenceResponse
from app.models.evidence import EvidenceCreate, EvidenceSourceType
from app.models.evidence_mapping import EvidenceRelevance
from app.models.evidence import EvidenceStatus
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.services.evidence import EvidenceService
from app.services.evidence_mapping import EvidenceMappingService
from app.services.goal import GoalService

router = APIRouter(prefix="/goals", tags=["goal-evidence"])


class GoalEvidenceCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    source_type: EvidenceSourceType
    source_id: str | None = None
    source_url: str | None = None
    content_hash: str | None = None
    captured_at: datetime
    relevance: EvidenceRelevance


def get_goal_service(db: Annotated[Session, Depends(get_db)]) -> GoalService:
    return GoalService(db)


def get_evidence_service(db: Annotated[Session, Depends(get_db)]) -> EvidenceService:
    return EvidenceService(db)


def get_evidence_mapping_service(
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceMappingService:
    return EvidenceMappingService(db)


def _require_goal(goal, user_id: str):
    if goal is None or goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    return goal


def _normalized_title(title: str) -> str:
    return " ".join(title.casefold().split())


def _normalized_url(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    parsed = urlsplit(url.strip())
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            parsed.query,
            parsed.fragment,
        )
    )


@router.post(
    "/{goal_id}/evidence",
    response_model=GoalEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_goal_evidence(
    goal_id: str,
    request: GoalEvidenceCreateRequest,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    evidence_service: Annotated[EvidenceService, Depends(get_evidence_service)],
    mapping_service: Annotated[EvidenceMappingService, Depends(get_evidence_mapping_service)],
) -> GoalEvidenceResponse:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)

    mappings = mapping_service.get_mappings_by_goal_id(goal_id)
    mapped_evidence = [
        evidence_service.get_evidence_by_id(mapping.evidence_id)
        for mapping in mappings
    ]
    normalized_title = _normalized_title(request.title)
    normalized_url = _normalized_url(request.source_url)
    for existing in mapped_evidence:
        if existing is None or existing.user_id != user_id:
            continue
        same_title = _normalized_title(existing.title) == normalized_title
        same_source = bool(
            (request.source_id and existing.source_id == request.source_id)
            or (request.content_hash and existing.content_hash == request.content_hash)
            or (
                normalized_url
                and _normalized_url(existing.source_url) == normalized_url
            )
        )
        if same_title or same_source:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Duplicate evidence: '{existing.title}' is already attached to this goal.",
            )

    existing_evidence = None
    if request.source_id:
        existing_evidence = evidence_service.get_evidence_by_source(
            request.source_type,
            request.source_id,
        )
        if existing_evidence is not None and existing_evidence.user_id != user_id:
            existing_evidence = None
    if existing_evidence is None and request.content_hash:
        existing_evidence = next(
            (
                item
                for item in evidence_service.get_evidence_by_user_id(user_id)
                if item.content_hash == request.content_hash
            ),
            None,
        )
    if existing_evidence is None and normalized_url:
        existing_evidence = next(
            (
                item
                for item in evidence_service.get_evidence_by_user_id(user_id)
                if _normalized_url(item.source_url) == normalized_url
            ),
            None,
        )

    evidence = existing_evidence or evidence_service.create_evidence(
        EvidenceCreate(
            user_id=user_id,
            source_type=request.source_type,
            source_id=request.source_id,
            title=request.title.strip(),
            description=request.description,
            source_url=request.source_url,
            content_hash=request.content_hash,
            captured_at=request.captured_at,
        )
    )
    try:
        mapping = mapping_service.create_mapping(
            evidence_id=evidence.id,
            goal_id=goal_id,
            relevance=request.relevance,
            confidence=1.0,
            reason="Added by the user from this goal's detail page.",
        )
    except EvidenceMappingAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return GoalEvidenceResponse(
        evidence_id=evidence.id,
        title=evidence.title,
        description=evidence.description,
        source_type=evidence.source_type.value,
        source_url=evidence.source_url,
        captured_at=evidence.captured_at,
        relevance=mapping.relevance.value,
        confidence=mapping.confidence,
        reason=mapping.reason,
    )


@router.get("/{goal_id}/evidence", response_model=list[GoalEvidenceResponse])
def get_goal_evidence(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    evidence_service: Annotated[EvidenceService, Depends(get_evidence_service)],
    mapping_service: Annotated[
        EvidenceMappingService,
        Depends(get_evidence_mapping_service),
    ],
) -> list[GoalEvidenceResponse]:
    _require_goal(goal_service.get_goal_by_id(goal_id), user_id)

    responses: list[GoalEvidenceResponse] = []
    for mapping in mapping_service.get_mappings_by_goal_id(goal_id):
        evidence = evidence_service.get_evidence_by_id(mapping.evidence_id)
        if (
            evidence is None
            or evidence.user_id != user_id
            or evidence.status != EvidenceStatus.ACTIVE
        ):
            continue
        responses.append(
            GoalEvidenceResponse(
                evidence_id=evidence.id,
                title=evidence.title,
                description=evidence.description,
                source_type=evidence.source_type.value,
                source_url=getattr(evidence, "source_url", None),
                captured_at=evidence.captured_at,
                relevance=mapping.relevance.value,
                confidence=mapping.confidence,
                reason=mapping.reason,
            )
        )

    return responses
