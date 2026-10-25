from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.goals import get_goal_service
from app.api.v1.milestones import get_milestone_service
from app.db.session import get_db
from app.models.archive import (
    ArchivedEvidenceResponse,
    ArchivedMilestoneResponse,
    ArchivesResponse,
)
from app.models.api_v1_goals import GoalResponse
from app.models.evidence import EvidenceStatus
from app.models.goal import GoalStatus
from app.services.evidence import EvidenceService
from app.services.evidence_mapping import EvidenceMappingService
from app.services.goal import GoalService
from app.services.milestone import MilestoneService

router = APIRouter(tags=["archives"])


def get_evidence_service(db: Annotated[Session, Depends(get_db)]) -> EvidenceService:
    return EvidenceService(db)


def get_evidence_mapping_service(
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceMappingService:
    return EvidenceMappingService(db)


@router.get("/archives", response_model=ArchivesResponse)
def list_archives(
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    evidence_service: Annotated[EvidenceService, Depends(get_evidence_service)],
    mapping_service: Annotated[
        EvidenceMappingService,
        Depends(get_evidence_mapping_service),
    ],
    milestone_service: Annotated[MilestoneService, Depends(get_milestone_service)],
) -> ArchivesResponse:
    user_goals = goal_service.get_goals_by_user_id(user_id)
    goals_by_id = {goal.id: goal for goal in user_goals}
    archived_goals = [
        goal for goal in user_goals if goal.status == GoalStatus.ARCHIVED
    ]

    archived_evidence = []
    for evidence in evidence_service.get_evidence_by_user_id(user_id):
        if evidence.status != EvidenceStatus.ARCHIVED or evidence.archived_at is None:
            continue
        goal_titles = sorted(
            {
                goals_by_id[mapping.goal_id].title
                for mapping in mapping_service.get_mappings_by_evidence_id(evidence.id)
                if mapping.goal_id in goals_by_id
            }
        )
        archived_evidence.append(
            ArchivedEvidenceResponse(
                id=evidence.id,
                title=evidence.title,
                description=evidence.description,
                source_type=evidence.source_type.value,
                source_url=evidence.source_url,
                captured_at=evidence.captured_at,
                archived_at=evidence.archived_at,
                goal_titles=goal_titles,
            )
        )

    archived_milestones = []
    for goal in user_goals:
        for milestone in milestone_service.get_milestones_by_goal_id(
            goal.id,
            include_archived=True,
        ):
            if milestone.archived_at is None:
                continue
            archived_milestones.append(
                ArchivedMilestoneResponse(
                    id=milestone.id,
                    goal_id=goal.id,
                    goal_title=goal.title,
                    title=milestone.title,
                    description=milestone.description,
                    completion_criteria=milestone.completion_criteria,
                    status=milestone.status,
                    source=milestone.source,
                    due_date=milestone.due_date,
                    archived_at=milestone.archived_at,
                )
            )

    return ArchivesResponse(
        goals=[
            GoalResponse.model_validate(goal, from_attributes=True)
            for goal in archived_goals
        ],
        evidence=archived_evidence,
        milestones=archived_milestones,
    )


@router.post("/evidence/{evidence_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_evidence(
    evidence_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    evidence_service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> None:
    evidence = evidence_service.get_evidence_by_id(evidence_id)
    if evidence is None or evidence.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    try:
        evidence_service.archive_evidence(evidence_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_archived_evidence(
    evidence_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    evidence_service: Annotated[EvidenceService, Depends(get_evidence_service)],
) -> None:
    evidence = evidence_service.get_evidence_by_id(evidence_id)
    if evidence is None or evidence.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    if evidence.status != EvidenceStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only archived evidence can be deleted",
        )
    evidence_service.delete_archived_evidence(evidence_id)
