from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoalBaselineObservationDB(Base):
    __tablename__ = "goal_baseline_observations"

    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), primary_key=True
    )
    goal_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    historical_effectivity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["goal_version_id", "goal_id"],
            ["goal_versions.id", "goal_versions.goal_id"],
            name="fk_goal_baseline_observation_version",
        ),
        CheckConstraint(
            "historical_effectivity = 'UNKNOWN'", name="ck_goal_baseline_observation_history"
        ),
    )
