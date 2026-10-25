from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrganizationRoleDB(Base):
    __tablename__ = "organization_roles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "normalized_name",
            name="uq_organization_roles_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    responsibilities: Mapped[list["OrganizationRoleResponsibilityDB"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        order_by="OrganizationRoleResponsibilityDB.position",
    )
    goals: Mapped[list["OrganizationRoleGoalDB"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        order_by="OrganizationRoleGoalDB.position",
    )
    competencies: Mapped[list["OrganizationRoleCompetencyDB"]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
        order_by="OrganizationRoleCompetencyDB.position",
    )


class OrganizationRoleResponsibilityDB(Base):
    __tablename__ = "organization_role_responsibilities"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "position",
            name="uq_organization_role_responsibility_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("organization_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    statement: Mapped[str] = mapped_column(String(2000), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    role: Mapped[OrganizationRoleDB] = relationship(back_populates="responsibilities")


class OrganizationRoleGoalDB(Base):
    __tablename__ = "organization_role_goals"
    __table_args__ = (
        UniqueConstraint("role_id", "position", name="uq_organization_role_goal_position"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("organization_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    role: Mapped[OrganizationRoleDB] = relationship(back_populates="goals")


class OrganizationRoleCompetencyDB(Base):
    __tablename__ = "organization_role_competencies"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "position",
            name="uq_organization_role_competency_position",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("organization_roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    expected_level: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(2000))
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    role: Mapped[OrganizationRoleDB] = relationship(back_populates="competencies")


class OrganizationRoleAuditEventDB(Base):
    __tablename__ = "organization_role_audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role_name: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(200), nullable=False)
    before_snapshot: Mapped[dict | None] = mapped_column(JSON)
    after_snapshot: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
