from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.impact_assessment import ImpactAssessment, ImpactType
from app.services.impact_assessment import ImpactAssessmentService


class ImpactAssessmentCreateRequest(BaseModel):
    evidence_id: str
    goal_id: str
    impact_type: ImpactType
    impact_summary: str
    impact_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    assessment_version: int | None = Field(default=None, ge=1)


router = APIRouter(
    prefix="/impact-assessments",
    tags=["impact-assessments"],
)


def get_impact_assessment_service(
    db: Annotated[Session, Depends(get_db)],
) -> ImpactAssessmentService:
    return ImpactAssessmentService(db)


@router.post(
    "",
    response_model=ImpactAssessment,
    status_code=status.HTTP_201_CREATED,
)
def create_impact_assessment(
    request: ImpactAssessmentCreateRequest,
    service: Annotated[
        ImpactAssessmentService,
        Depends(get_impact_assessment_service),
    ],
) -> ImpactAssessment:
    assessment = service.create_assessment(
        evidence_id=request.evidence_id,
        goal_id=request.goal_id,
        impact_type=request.impact_type,
        impact_summary=request.impact_summary,
        impact_score=request.impact_score,
        confidence=request.confidence,
        assessment_version=request.assessment_version,
    )

    return ImpactAssessment.model_validate(
        assessment,
        from_attributes=True,
    )


@router.get(
    "/evidence/{evidence_id}/goal/{goal_id}",
    response_model=ImpactAssessment,
)
def get_assessment_by_evidence_and_goal(
    evidence_id: str,
    goal_id: str,
    service: Annotated[
        ImpactAssessmentService,
        Depends(get_impact_assessment_service),
    ],
) -> ImpactAssessment:
    assessment = service.get_assessment_by_evidence_and_goal(
        evidence_id,
        goal_id,
    )

    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impact assessment not found",
        )

    return ImpactAssessment.model_validate(
        assessment,
        from_attributes=True,
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=list[ImpactAssessment],
)
def get_assessments_by_evidence_id(
    evidence_id: str,
    service: Annotated[
        ImpactAssessmentService,
        Depends(get_impact_assessment_service),
    ],
) -> list[ImpactAssessment]:
    assessments = service.get_assessments_by_evidence_id(evidence_id)
    return [
        ImpactAssessment.model_validate(
            assessment,
            from_attributes=True,
        )
        for assessment in assessments
    ]


@router.get(
    "/goal/{goal_id}",
    response_model=list[ImpactAssessment],
)
def get_assessments_by_goal_id(
    goal_id: str,
    service: Annotated[
        ImpactAssessmentService,
        Depends(get_impact_assessment_service),
    ],
) -> list[ImpactAssessment]:
    assessments = service.get_assessments_by_goal_id(goal_id)
    return [
        ImpactAssessment.model_validate(
            assessment,
            from_attributes=True,
        )
        for assessment in assessments
    ]


@router.get(
    "/{assessment_id}",
    response_model=ImpactAssessment,
)
def get_assessment_by_id(
    assessment_id: str,
    service: Annotated[
        ImpactAssessmentService,
        Depends(get_impact_assessment_service),
    ],
) -> ImpactAssessment:
    assessment = service.get_assessment_by_id(assessment_id)

    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impact assessment not found",
        )

    return ImpactAssessment.model_validate(
        assessment,
        from_attributes=True,
    )
