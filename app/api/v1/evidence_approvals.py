from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_approval import EvidenceApprovalDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.goal import GoalDB
from app.db.models.milestone import MilestoneDB
from app.db.models.notification import NotificationDB
from app.db.models.notification_history import NotificationHistoryDB
from app.db.models.notification_response import NotificationResponseDB
from app.db.models.user import UserDB
from app.db.session import get_db
from app.models.evidence_approval import EvidenceApprovalStatus
from app.models.evidence import EvidenceStatus
from app.models.notification import NotificationStatus
from app.services.notification_history import add_notification_history

router = APIRouter(tags=["evidence-approvals", "notifications"])


class PendingEvidenceApprovalResponse(BaseModel):
    approval_id: str
    evidence_id: str
    employee_id: str
    employee_name: str
    goal_id: str
    goal_title: str
    goal_description: str | None
    goal_status: str
    goal_start_date: str | None
    goal_end_date: str | None
    milestone_id: str | None
    milestone_title: str | None
    milestone_description: str | None
    milestone_completion_criteria: str | None
    milestone_status: str | None
    milestone_due_date: str | None
    evidence_title: str
    evidence_description: str | None
    evidence_source_type: str
    evidence_source_url: str | None
    evidence_captured_at: datetime
    relevance: str
    confidence: float
    reason: str | None
    submitted_at: datetime


class EvidenceApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected", "needs_information"]
    comment: str | None = Field(default=None, max_length=4000)


class EvidenceApprovalResponse(BaseModel):
    id: str
    status: EvidenceApprovalStatus
    manager_comment: str | None
    reviewed_at: datetime | None


class EvidenceResubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    source_url: str | None = Field(default=None, max_length=2000)
    notes: str = Field(min_length=1, max_length=4000)

    @field_validator("title", "notes")
    @classmethod
    def trim_nonblank_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("This field must not be blank.")
        return trimmed


class EvidenceResubmissionResponse(BaseModel):
    approval_id: str
    evidence_id: str
    status: EvidenceApprovalStatus
    notification_id: str


class NotificationResponseEntry(BaseModel):
    id: str
    user_id: str
    response_text: str | None
    metadata: dict[str, Any]
    created_at: datetime


class NotificationHistoryEntry(BaseModel):
    id: str
    event_type: str
    actor_user_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    related_path: str | None
    status: NotificationStatus
    metadata: dict[str, Any]
    created_at: datetime
    read_at: datetime | None
    responses: list[NotificationResponseEntry] = Field(default_factory=list)
    history: list[NotificationHistoryEntry] = Field(default_factory=list)


def _notification_response(
    db: Session,
    notification: NotificationDB,
) -> NotificationResponse:
    responses = db.scalars(
        select(NotificationResponseDB)
        .where(NotificationResponseDB.notification_id == notification.id)
        .order_by(NotificationResponseDB.created_at, NotificationResponseDB.id)
    ).all()
    history = db.scalars(
        select(NotificationHistoryDB)
        .where(NotificationHistoryDB.notification_id == notification.id)
        .order_by(NotificationHistoryDB.created_at, NotificationHistoryDB.id)
    ).all()
    return NotificationResponse(
        id=notification.id,
        title=notification.title,
        message=notification.message,
        related_path=notification.related_path,
        status=notification.status,
        metadata=notification.metadata_json,
        created_at=notification.created_at,
        read_at=notification.read_at,
        responses=[
            NotificationResponseEntry(
                id=response.id,
                user_id=response.user_id,
                response_text=response.response_text,
                metadata=response.metadata_json,
                created_at=response.created_at,
            )
            for response in responses
        ],
        history=[
            NotificationHistoryEntry(
                id=item.id,
                event_type=item.event_type,
                actor_user_id=item.actor_user_id,
                metadata=item.metadata_json,
                created_at=item.created_at,
            )
            for item in history
        ],
    )


@router.get(
    "/evidence-approvals/pending",
    response_model=list[PendingEvidenceApprovalResponse],
)
def list_pending_evidence_approvals(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[PendingEvidenceApprovalResponse]:
    rows = db.execute(
        select(
            EvidenceApprovalDB,
            EvidenceMappingDB,
            EvidenceDB,
            GoalDB,
            UserDB,
            MilestoneDB,
        )
        .join(EvidenceMappingDB, EvidenceApprovalDB.mapping_id == EvidenceMappingDB.id)
        .join(EvidenceDB, EvidenceMappingDB.evidence_id == EvidenceDB.id)
        .join(GoalDB, EvidenceMappingDB.goal_id == GoalDB.id)
        .join(UserDB, EvidenceDB.user_id == UserDB.id)
        .outerjoin(MilestoneDB, EvidenceMappingDB.milestone_id == MilestoneDB.id)
        .where(
            UserDB.reporting_manager_id == current_user.user_id,
            GoalDB.user_id == EvidenceDB.user_id,
            EvidenceApprovalDB.status == EvidenceApprovalStatus.PENDING,
            EvidenceDB.status == EvidenceStatus.ACTIVE,
        )
        .order_by(EvidenceApprovalDB.created_at, EvidenceApprovalDB.id)
    ).all()
    return [
        PendingEvidenceApprovalResponse(
            approval_id=approval.id,
            evidence_id=evidence.id,
            employee_id=employee.id,
            employee_name=employee.name,
            goal_id=goal.id,
            goal_title=goal.title,
            goal_description=goal.description,
            goal_status=goal.status.value,
            goal_start_date=goal.start_date.isoformat() if goal.start_date else None,
            goal_end_date=goal.end_date.isoformat() if goal.end_date else None,
            milestone_id=milestone.id if milestone else None,
            milestone_title=milestone.title if milestone else None,
            milestone_description=milestone.description if milestone else None,
            milestone_completion_criteria=(
                milestone.completion_criteria if milestone else None
            ),
            milestone_status=milestone.status.value if milestone else None,
            milestone_due_date=(
                milestone.due_date.isoformat() if milestone and milestone.due_date else None
            ),
            evidence_title=evidence.title,
            evidence_description=evidence.description,
            evidence_source_type=evidence.source_type.value,
            evidence_source_url=evidence.source_url,
            evidence_captured_at=evidence.captured_at,
            relevance=mapping.relevance.value,
            confidence=mapping.confidence,
            reason=mapping.reason,
            submitted_at=approval.created_at,
        )
        for approval, mapping, evidence, goal, employee, milestone in rows
    ]


@router.post(
    "/evidence-approvals/{approval_id}/decision",
    response_model=EvidenceApprovalResponse,
)
def decide_evidence_approval(
    approval_id: str,
    request: EvidenceApprovalDecisionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceApprovalResponse:
    result = db.execute(
        select(EvidenceApprovalDB, EvidenceMappingDB, EvidenceDB, GoalDB, UserDB)
        .join(EvidenceMappingDB, EvidenceApprovalDB.mapping_id == EvidenceMappingDB.id)
        .join(EvidenceDB, EvidenceMappingDB.evidence_id == EvidenceDB.id)
        .join(GoalDB, EvidenceMappingDB.goal_id == GoalDB.id)
        .join(UserDB, EvidenceDB.user_id == UserDB.id)
        .where(
            EvidenceApprovalDB.id == approval_id,
            GoalDB.user_id == EvidenceDB.user_id,
        )
        .with_for_update(of=EvidenceApprovalDB)
    ).first()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence approval not found.",
        )

    approval, _mapping, evidence, goal, employee = result
    if employee.reporting_manager_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the employee's reporting manager can review this evidence.",
        )
    if approval.status != EvidenceApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This evidence approval has already been reviewed.",
        )

    reviewed_at = datetime.now(UTC)
    decision = EvidenceApprovalStatus(request.decision)
    approval.status = decision
    approval.reviewed_by_user_id = current_user.user_id
    approval.manager_comment = request.comment.strip() if request.comment else None
    approval.reviewed_at = reviewed_at

    decision_label = {
        EvidenceApprovalStatus.APPROVED: "approved",
        EvidenceApprovalStatus.REJECTED: "rejected",
        EvidenceApprovalStatus.NEEDS_INFORMATION: "requested more information for",
    }[decision]
    notification_message = (
        f'Your manager {decision_label} the evidence "{evidence.title}" '
        f'for goal "{goal.title}".'
    )
    if approval.manager_comment:
        notification_message += f" Manager comment: {approval.manager_comment}"
    notification_metadata = {
        "status": NotificationStatus.UNREAD.value,
        "reason": decision.value,
        "notes": approval.manager_comment,
        "approval_id": approval.id,
        "evidence_id": evidence.id,
        "goal_id": goal.id,
    }
    notification = NotificationDB(
        id=str(uuid4()),
        user_id=employee.id,
        title="Evidence review update",
        message=notification_message,
        related_path=f"/goals/{goal.id}",
        evidence_approval_id=approval.id,
        status=NotificationStatus.UNREAD,
        metadata_json=notification_metadata,
        created_at=reviewed_at,
    )
    db.add(notification)
    db.flush()
    add_notification_history(
        db,
        notification_id=notification.id,
        evidence_approval_id=approval.id,
        actor_user_id=current_user.user_id,
        event_type="manager_decision_sent",
        metadata=notification_metadata,
        created_at=reviewed_at,
    )
    db.commit()
    db.refresh(approval)
    return EvidenceApprovalResponse(
        id=approval.id,
        status=approval.status,
        manager_comment=approval.manager_comment,
        reviewed_at=approval.reviewed_at,
    )


@router.post(
    "/evidence-approvals/{approval_id}/resubmit",
    response_model=EvidenceResubmissionResponse,
)
def resubmit_evidence_approval(
    approval_id: str,
    request: EvidenceResubmissionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceResubmissionResponse:
    result = db.execute(
        select(EvidenceApprovalDB, EvidenceMappingDB, EvidenceDB, GoalDB, UserDB)
        .join(EvidenceMappingDB, EvidenceApprovalDB.mapping_id == EvidenceMappingDB.id)
        .join(EvidenceDB, EvidenceMappingDB.evidence_id == EvidenceDB.id)
        .join(GoalDB, EvidenceMappingDB.goal_id == GoalDB.id)
        .join(UserDB, EvidenceDB.user_id == UserDB.id)
        .where(
            EvidenceApprovalDB.id == approval_id,
            GoalDB.user_id == EvidenceDB.user_id,
        )
        .with_for_update(of=EvidenceApprovalDB)
    ).first()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence approval not found.",
        )

    approval, _mapping, evidence, goal, employee = result
    if employee.id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the evidence owner can resubmit this evidence.",
        )
    if approval.status not in {
        EvidenceApprovalStatus.REJECTED,
        EvidenceApprovalStatus.NEEDS_INFORMATION,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only rejected evidence or evidence needing more information can be resubmitted.",
        )
    if employee.reporting_manager_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assign a reporting manager before resubmitting evidence.",
        )
    manager = db.get(UserDB, employee.reporting_manager_id)
    if manager is None or not manager.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active reporting manager is required to resubmit evidence.",
        )

    now = datetime.now(UTC)
    prior_status = approval.status.value
    before = {
        "title": evidence.title,
        "description": evidence.description,
        "source_url": evidence.source_url,
    }
    if request.title is not None:
        evidence.title = request.title
    if "description" in request.model_fields_set:
        evidence.description = request.description
    if "source_url" in request.model_fields_set:
        evidence.source_url = request.source_url.strip() if request.source_url else None
    evidence.updated_at = now
    after = {
        "title": evidence.title,
        "description": evidence.description,
        "source_url": evidence.source_url,
    }

    approval.status = EvidenceApprovalStatus.PENDING
    approval.reviewed_by_user_id = None
    approval.manager_comment = None
    approval.reviewed_at = None
    approval.created_at = now

    response_metadata = {
        "status": EvidenceApprovalStatus.PENDING.value,
        "reason": prior_status,
        "notes": request.notes,
        "approval_id": approval.id,
        "evidence_id": evidence.id,
        "goal_id": goal.id,
        "evidence_before": before,
        "evidence_after": after,
    }
    manager_message = (
        f"{employee.name} updated and resubmitted the evidence "
        f'"{evidence.title}" for goal "{goal.title}".'
    )
    if request.notes:
        manager_message += f" Employee note: {request.notes}"
    notification = NotificationDB(
        id=str(uuid4()),
        user_id=manager.id,
        title="Evidence resubmitted",
        message=manager_message,
        related_path=f"/goals/{goal.id}",
        evidence_approval_id=approval.id,
        status=NotificationStatus.UNREAD,
        metadata_json={
            **response_metadata,
            "status": NotificationStatus.UNREAD.value,
        },
        created_at=now,
    )
    db.add(notification)
    db.flush()

    response = NotificationResponseDB(
        id=str(uuid4()),
        notification_id=notification.id,
        user_id=employee.id,
        response_text=request.notes,
        metadata_json=response_metadata,
        created_at=now,
    )
    db.add(response)
    db.flush()
    add_notification_history(
        db,
        notification_id=notification.id,
        response_id=response.id,
        evidence_approval_id=approval.id,
        actor_user_id=employee.id,
        event_type="employee_resubmitted",
        metadata=response_metadata,
        created_at=now,
    )
    db.commit()
    return EvidenceResubmissionResponse(
        approval_id=approval.id,
        evidence_id=evidence.id,
        status=approval.status,
        notification_id=notification.id,
    )


@router.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[NotificationResponse]:
    notifications = db.scalars(
        select(NotificationDB)
        .where(NotificationDB.user_id == current_user.user_id)
        .order_by(NotificationDB.created_at.desc(), NotificationDB.id.desc())
    ).all()
    return [_notification_response(db, item) for item in notifications]


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
def mark_notification_read(
    notification_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationResponse:
    notification = db.scalar(
        select(NotificationDB).where(
            NotificationDB.id == notification_id,
            NotificationDB.user_id == current_user.user_id,
        )
    )
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    if notification.status != NotificationStatus.READ:
        notification.status = NotificationStatus.READ
        notification.read_at = datetime.now(UTC)
        notification_metadata = {
            **notification.metadata_json,
            "status": NotificationStatus.READ.value,
        }
        notification.metadata_json = notification_metadata
        add_notification_history(
            db,
            notification_id=notification.id,
            evidence_approval_id=notification.evidence_approval_id,
            actor_user_id=current_user.user_id,
            event_type="notification_read",
            metadata={
                "status": NotificationStatus.READ.value,
                "reason": "recipient_marked_read",
                "notes": None,
            },
            created_at=notification.read_at,
        )
        db.commit()
        db.refresh(notification)
    return _notification_response(db, notification)
