from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoalSourceFetchStateDB(Base):
    __tablename__ = "goal_source_fetch_states"

    goal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("goals.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_successful_fetch_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "provider IN ('github', 'jira')",
            name="ck_goal_source_fetch_state_provider",
        ),
    )
