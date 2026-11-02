from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
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
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, default="COMPLETE")
    error_category: Mapped[str | None] = mapped_column(String(40))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bounds: Mapped[dict | None] = mapped_column(JSON)
    coverage: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        CheckConstraint(
            "provider IN ('github', 'jira')",
            name="ck_goal_source_retrieval_provider",
        ),
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILURE')",
            name="ck_goal_source_retrieval_status",
        ),
        CheckConstraint(
            "outcome IN ('COMPLETE', 'PARTIAL', 'NO_RESULTS', 'INACCESSIBLE', 'FAILED')",
            name="ck_goal_source_retrieval_outcome",
        ),
        Index("ix_goal_source_retrievals_goal_checked", "goal_id", "checked_at"),
    )
