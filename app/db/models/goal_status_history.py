from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.goal import GoalStatus


class GoalStatusHistoryDB(Base):
    __tablename__ = "goal_status_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[GoalStatus] = mapped_column(
        Enum(GoalStatus, name="goal_status"), nullable=False
    )
    to_status: Mapped[GoalStatus] = mapped_column(
        Enum(GoalStatus, name="goal_status"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
