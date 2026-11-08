from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GoalVersionDB(Base):
    __tablename__ = "goal_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    goal = relationship("GoalDB", back_populates="versions")
    validation_runs = relationship(
        "GoalValidationRunDB",
        back_populates="goal_version",
        passive_deletes="all",
        order_by="GoalValidationRunDB.created_at",
        overlaps="validation_runs",
    )

    __table_args__ = (
        UniqueConstraint("goal_id", "version", name="uq_goal_version_number"),
        UniqueConstraint("id", "goal_id", name="uq_goal_version_id_goal"),
        CheckConstraint("version > 0", name="ck_goal_version_positive"),
        CheckConstraint("origin IN ('LEGACY', 'USER')", name="ck_goal_version_origin"),
        Index("ix_goal_versions_goal_version", "goal_id", "version"),
    )
