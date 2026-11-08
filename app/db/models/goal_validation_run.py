from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GoalValidationRunDB(Base):
    __tablename__ = "goal_validation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    goal_version_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    findings: Mapped[list] = mapped_column(JSON, nullable=False)
    input_context: Mapped[dict | None] = mapped_column(JSON)
    result_context: Mapped[dict | None] = mapped_column(JSON)
    rule_set_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(200))
    actor_user_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    goal = relationship(
        "GoalDB",
        back_populates="validation_runs",
        overlaps="validation_runs",
    )
    goal_version = relationship(
        "GoalVersionDB",
        back_populates="validation_runs",
        overlaps="goal,validation_runs",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('READY', 'NEEDS_IMPROVEMENT', 'NEEDS_REVIEW', "
            "'NEEDS_REFINEMENT', 'NEEDS_DISCUSSION', 'INVALID')",
            name="ck_goal_validation_run_status",
        ),
        ForeignKeyConstraint(
            ["goal_version_id", "goal_id"],
            ["goal_versions.id", "goal_versions.goal_id"],
            ondelete="CASCADE",
            name="fk_goal_validation_runs_version_goal",
        ),
        Index("ix_goal_validation_runs_goal_created", "goal_id", "created_at"),
        Index("ix_goal_validation_runs_version", "goal_version_id"),
    )
