from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus


class GoalDB(Base):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[GoalScope] = mapped_column(Enum(GoalScope, name="goal_scope"), nullable=False, default=GoalScope.PERSONAL)
    organization_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("organizations.id")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[GoalStatus] = mapped_column(Enum(GoalStatus, name="goal_status"), nullable=False, default=GoalStatus.DRAFT)
    sub_status: Mapped[GoalSubStatus] = mapped_column(Enum(GoalSubStatus, name="goal_sub_status"), nullable=False, default=GoalSubStatus.NEEDS_REVIEW)
    deactivation_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    source_document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    structured_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user = relationship("UserDB", back_populates="goals")
    organization = relationship("OrganizationDB")
    source_document = relationship("DocumentDB")
    evidence_mappings = relationship(
        "EvidenceMappingDB",
        back_populates="goal",
        cascade="all, delete-orphan",
    )
    impact_assessments = relationship(
        "ImpactAssessmentDB",
        back_populates="goal",
        cascade="all, delete-orphan",
    )
    milestones = relationship("MilestoneDB", back_populates="goal", cascade="all, delete-orphan")
    criteria = relationship(
        "GoalCriterionDB",
        back_populates="goal",
        cascade="all, delete-orphan",
    )
    versions = relationship(
        "GoalVersionDB",
        back_populates="goal",
        passive_deletes="all",
        order_by="GoalVersionDB.version",
    )
    validation_runs = relationship(
        "GoalValidationRunDB",
        back_populates="goal",
        passive_deletes="all",
        order_by="GoalValidationRunDB.created_at",
    )

    @property
    def organization_name(self) -> str | None:
        if self.organization_id is None:
            return None
        return self.organization.name if self.organization is not None else None
