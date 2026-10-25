from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoalSourceRetrievalDB(Base):
    __tablename__ = "goal_source_retrievals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("goal_assessment_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    used_snapshot: Mapped[bool] = mapped_column(nullable=False, default=False)
    snapshot_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "provider IN ('github', 'jira')",
            name="ck_goal_source_retrieval_provider",
        ),
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILURE')",
            name="ck_goal_source_retrieval_status",
        ),
        Index("ix_goal_source_retrievals_goal_checked", "goal_id", "checked_at"),
    )
