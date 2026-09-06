from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.models.evidence_mapping import EvidenceMapping, EvidenceRelevance
from app.services.evidence_mapping import EvidenceMappingService


class EvidenceMappingCreateRequest(BaseModel):
    evidence_id: str
    goal_id: str
    relevance: EvidenceRelevance
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str | None = None


router = APIRouter(
    prefix="/evidence-mappings",
    tags=["evidence-mappings"],
)


def get_evidence_mapping_service(
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceMappingService:
    return EvidenceMappingService(db)


@router.post(
    "",
    response_model=EvidenceMapping,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence_mapping(
    request: EvidenceMappingCreateRequest,
    service: Annotated[
        EvidenceMappingService,
        Depends(get_evidence_mapping_service),
    ],
) -> EvidenceMapping:
    try:
        mapping = service.create_mapping(
            evidence_id=request.evidence_id,
            goal_id=request.goal_id,
            relevance=request.relevance,
            confidence=request.confidence,
            reason=request.reason,
        )
    except EvidenceMappingAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return EvidenceMapping.model_validate(
        mapping,
        from_attributes=True,
    )


@router.get(
    "/evidence/{evidence_id}/goal/{goal_id}",
    response_model=EvidenceMapping,
)
def get_mapping_by_evidence_and_goal(
    evidence_id: str,
    goal_id: str,
    service: Annotated[
        EvidenceMappingService,
        Depends(get_evidence_mapping_service),
    ],
) -> EvidenceMapping:
    mapping = service.get_mapping_by_evidence_and_goal(
        evidence_id,
        goal_id,
    )

    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence mapping not found",
        )

    return EvidenceMapping.model_validate(
        mapping,
        from_attributes=True,
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=list[EvidenceMapping],
)
def get_mappings_by_evidence_id(
    evidence_id: str,
    service: Annotated[
        EvidenceMappingService,
        Depends(get_evidence_mapping_service),
    ],
) -> list[EvidenceMapping]:
    mappings = service.get_mappings_by_evidence_id(evidence_id)
    return [
        EvidenceMapping.model_validate(
            mapping,
            from_attributes=True,
        )
        for mapping in mappings
    ]


@router.get(
    "/goal/{goal_id}",
    response_model=list[EvidenceMapping],
)
def get_mappings_by_goal_id(
    goal_id: str,
    service: Annotated[
        EvidenceMappingService,
        Depends(get_evidence_mapping_service),
    ],
) -> list[EvidenceMapping]:
    mappings = service.get_mappings_by_goal_id(goal_id)
    return [
        EvidenceMapping.model_validate(
            mapping,
            from_attributes=True,
        )
        for mapping in mappings
    ]


@router.get(
    "/{mapping_id}",
    response_model=EvidenceMapping,
)
def get_mapping_by_id(
    mapping_id: str,
    service: Annotated[
        EvidenceMappingService,
        Depends(get_evidence_mapping_service),
    ],
) -> EvidenceMapping:
    mapping = service.get_mapping_by_id(mapping_id)

    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence mapping not found",
        )

    return EvidenceMapping.model_validate(
        mapping,
        from_attributes=True,
    )
