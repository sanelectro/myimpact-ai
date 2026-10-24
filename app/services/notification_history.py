from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.notification_history import NotificationHistoryDB


def add_notification_history(
    db: Session,
    *,
    event_type: str,
    metadata: dict[str, object],
    notification_id: str | None = None,
    response_id: str | None = None,
    evidence_approval_id: str | None = None,
    actor_user_id: str | None = None,
    created_at: datetime | None = None,
) -> NotificationHistoryDB:
    history = NotificationHistoryDB(
        id=str(uuid4()),
        notification_id=notification_id,
        response_id=response_id,
        evidence_approval_id=evidence_approval_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        metadata_json=metadata,
        created_at=created_at or datetime.now(UTC),
    )
    db.add(history)
    return history
