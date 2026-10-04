from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_v1_impact import GoalEvidenceResponse
from app.services.evidence import EvidenceService
from app.services.evidence_mapping import EvidenceMappingService
from app.services.goal import GoalService

router = APIRouter(prefix="/goals", tags=["goal-evidence"])


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
        if evidence is None or evidence.user_id != user_id:
            continue
        responses.append(
            GoalEvidenceResponse(
                evidence_id=evidence.id,
                title=evidence.title,
                description=evidence.description,
                source_type=evidence.source_type.value,
                captured_at=evidence.captured_at,
                relevance=mapping.relevance.value,
                confidence=mapping.confidence,
                reason=mapping.reason,
            )
        )

    return responses
