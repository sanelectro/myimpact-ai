from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.evidence_version import EvidenceVersion
from app.services.evidence_version import EvidenceVersionService


class EvidenceVersionCreateRequest(BaseModel):
    evidence_id: str
    content: str
    content_hash: str
    source_updated_at: datetime | None = None
    captured_at: datetime


router = APIRouter(
    prefix="/evidence-versions",
    tags=["evidence-versions"],
)


def get_evidence_version_service(
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceVersionService:
    return EvidenceVersionService(db)


@router.post(
    "",
    response_model=EvidenceVersion,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence_version(
    request: EvidenceVersionCreateRequest,
    service: Annotated[
        EvidenceVersionService,
        Depends(get_evidence_version_service),
    ],
) -> EvidenceVersion:
    version = service.create_version(
        evidence_id=request.evidence_id,
        content=request.content,
        content_hash=request.content_hash,
        captured_at=request.captured_at,
        source_updated_at=request.source_updated_at,
    )
    return EvidenceVersion.model_validate(
        version,
        from_attributes=True,
    )


@router.get(
    "/evidence/{evidence_id}/version/{version}",
    response_model=EvidenceVersion,
)
def get_evidence_version(
    evidence_id: str,
    version: int,
    service: Annotated[
        EvidenceVersionService,
        Depends(get_evidence_version_service),
    ],
) -> EvidenceVersion:
    version_record = service.get_version(evidence_id, version)

    if version_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence version not found",
        )

    return EvidenceVersion.model_validate(
        version_record,
        from_attributes=True,
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=list[EvidenceVersion],
)
def get_evidence_versions(
    evidence_id: str,
    service: Annotated[
        EvidenceVersionService,
        Depends(get_evidence_version_service),
    ],
) -> list[EvidenceVersion]:
    versions = service.get_versions_by_evidence_id(evidence_id)
    return [
        EvidenceVersion.model_validate(
            version_record,
            from_attributes=True,
        )
        for version_record in versions
    ]


@router.get(
    "/{version_id}",
    response_model=EvidenceVersion,
)
def get_evidence_version_by_id(
    version_id: str,
    service: Annotated[
        EvidenceVersionService,
        Depends(get_evidence_version_service),
    ],
) -> EvidenceVersion:
    version_record = service.get_version_by_id(version_id)

    if version_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence version not found",
        )

    return EvidenceVersion.model_validate(
        version_record,
        from_attributes=True,
    )
