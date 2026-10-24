from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    role: Mapped[str | None] = mapped_column(String(200))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("organizations.id")
    )
    team_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("teams.id"))
    reporting_manager_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    goals = relationship("GoalDB", back_populates="user")
    evidence = relationship("EvidenceDB", back_populates="user")
    reports = relationship("ReportDB", back_populates="user")
    organization = relationship("OrganizationDB", foreign_keys=[organization_id])
    reporting_manager = relationship("UserDB", remote_side=[id], foreign_keys=[reporting_manager_id])
