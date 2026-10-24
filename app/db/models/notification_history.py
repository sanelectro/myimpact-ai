from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSON_METADATA = JSON().with_variant(JSONB(), "postgresql")


class NotificationHistoryDB(Base):
    __tablename__ = "notification_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notification_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("notifications.id", ondelete="SET NULL")
    )
    response_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("notification_responses.id", ondelete="SET NULL"),
    )
    evidence_approval_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("evidence_approvals.id", ondelete="CASCADE"),
        index=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_METADATA, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
