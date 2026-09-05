from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence import Evidence, EvidenceCreate, EvidenceSourceType
from app.services.evidence import EvidenceService

router = APIRouter(prefix="/evidence", tags=["evidence"])


def get_evidence_service(
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceService:
    return EvidenceService(db)


@router.post(
    "",
    response_model=Evidence,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence(
    evidence_data: EvidenceCreate,
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> Evidence:
    evidence = service.create_evidence(evidence_data)
    return Evidence.model_validate(evidence, from_attributes=True)


@router.get(
    "/source",
    response_model=Evidence | None,
)
def get_evidence_by_source(
    source_type: EvidenceSourceType,
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
    source_id: Annotated[str | None, Query()] = None,
) -> Evidence | None:
    evidence = service.get_evidence_by_source(source_type, source_id)

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found",
        )

    return Evidence.model_validate(evidence, from_attributes=True)


@router.get(
    "/user/{user_id}",
    response_model=list[Evidence],
)
def get_evidence_by_user_id(
    user_id: str,
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> list[Evidence]:
    evidence_items = service.get_evidence_by_user_id(user_id)
    return [
        Evidence.model_validate(item, from_attributes=True)
        for item in evidence_items
    ]


@router.get(
    "/{evidence_id}",
    response_model=Evidence,
)
def get_evidence_by_id(
    evidence_id: str,
    service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> Evidence:
    evidence = service.get_evidence_by_id(evidence_id)

    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found",
        )

    return Evidence.model_validate(evidence, from_attributes=True)
