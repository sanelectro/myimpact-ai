from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoalVersionApprovalDB(Base):
    __tablename__ = "goal_version_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    goal_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("goal_version_id", name="uq_goal_version_approval_version"),
        ForeignKeyConstraint(
            ["goal_version_id", "goal_id"],
            ["goal_versions.id", "goal_versions.goal_id"],
            ondelete="CASCADE",
            name="fk_goal_version_approvals_version_goal",
        ),
        Index("ix_goal_version_approvals_goal_created", "goal_id", "created_at"),
    )
