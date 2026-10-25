from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.goal_criteria import (
    GoalAssessmentFeedbackType,
    GoalAssessmentLifecycle,
    GoalAssessmentRunStatus,
    GoalCriterionApprovalStatus,
    GoalCriterionResult,
    GoalCriterionType,
)


class GoalCriterionDB(Base):
    __tablename__ = "goal_criteria"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_version: Mapped[int | None] = mapped_column(Integer)
    is_retired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    goal = relationship("GoalDB", back_populates="criteria")
    versions = relationship(
        "GoalCriterionVersionDB",
        back_populates="criterion",
        cascade="all, delete-orphan",
        order_by="GoalCriterionVersionDB.version",
    )


class GoalCriterionVersionDB(Base):
    __tablename__ = "goal_criterion_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    criterion_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goal_criteria.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    criterion_type: Mapped[GoalCriterionType] = mapped_column(
        Enum(GoalCriterionType, name="goal_criterion_type"), nullable=False
    )
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    approval_status: Mapped[GoalCriterionApprovalStatus] = mapped_column(
        Enum(GoalCriterionApprovalStatus, name="goal_criterion_approval_status"),
        nullable=False,
        default=GoalCriterionApprovalStatus.PROPOSED,
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    criterion = relationship("GoalCriterionDB", back_populates="versions")
    created_by = relationship("UserDB", foreign_keys=[created_by_user_id])
    approved_by = relationship("UserDB", foreign_keys=[approved_by_user_id])
    assessments = relationship("GoalCriterionAssessmentDB", back_populates="criterion_version")

    __table_args__ = (
        UniqueConstraint("criterion_id", "version", name="uq_goal_criterion_version"),
        CheckConstraint("version > 0", name="ck_goal_criterion_version_positive"),
    )


class GoalAssessmentRunDB(Base):
    __tablename__ = "goal_assessment_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), index=True)
    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[GoalAssessmentRunStatus] = mapped_column(
        Enum(GoalAssessmentRunStatus, name="goal_assessment_run_status"),
        nullable=False,
        default=GoalAssessmentRunStatus.PENDING,
    )
    trigger: Mapped[str] = mapped_column("trigger_type", String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    goal = relationship("GoalDB")
    requested_by = relationship("UserDB")
    assessments = relationship(
        "GoalCriterionAssessmentDB",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_goal_assessment_runs_goal_created", "goal_id", "created_at"),
    )


class GoalCriterionAssessmentDB(Base):
    __tablename__ = "goal_criterion_assessments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goal_assessment_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goal_criteria.id", ondelete="CASCADE"), nullable=False
    )
    criterion_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goal_criterion_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    result: Mapped[GoalCriterionResult] = mapped_column(
        Enum(GoalCriterionResult, name="goal_criterion_result"),
        nullable=False,
    )
    lifecycle_state: Mapped[GoalAssessmentLifecycle] = mapped_column(
        Enum(GoalAssessmentLifecycle, name="goal_assessment_lifecycle"),
        nullable=False,
        default=GoalAssessmentLifecycle.CURRENT,
    )
    progress_percentage: Mapped[int | None] = mapped_column(Integer)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    measured_value: Mapped[float | None] = mapped_column(Float)
    completed_milestone_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_version: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run = relationship("GoalAssessmentRunDB", back_populates="assessments")
    criterion = relationship("GoalCriterionDB")
    criterion_version = relationship("GoalCriterionVersionDB", back_populates="assessments")
    evidence = relationship(
        "GoalCriterionAssessmentEvidenceDB",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    events = relationship(
        "GoalCriterionAssessmentEventDB",
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="GoalCriterionAssessmentEventDB.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "progress_percentage IS NULL OR progress_percentage BETWEEN 0 AND 100",
            name="ck_goal_criterion_assessment_progress",
        ),
        CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_goal_criterion_assessment_confidence",
        ),
        Index(
            "ix_goal_criterion_assessments_criterion_created",
            "criterion_id",
            "created_at",
        ),
    )


class GoalCriterionAssessmentEvidenceDB(Base):
    __tablename__ = "goal_criterion_assessment_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goal_criterion_assessments.id", ondelete="CASCADE"), nullable=False
    )
    evidence_mapping_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evidence_mappings.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("evidence_versions.id", ondelete="SET NULL")
    )
    review_state: Mapped[str | None] = mapped_column(String(50))
    source_validity: Mapped[str] = mapped_column(String(50), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title_snapshot: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url_snapshot: Mapped[str | None] = mapped_column(String(2000))
    captured_at_snapshot: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at_snapshot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    citation_excerpt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    assessment = relationship("GoalCriterionAssessmentDB", back_populates="evidence")
    evidence_mapping = relationship("EvidenceMappingDB")
    evidence_version = relationship("EvidenceVersionDB")

    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "evidence_mapping_id",
            name="uq_goal_criterion_assessment_evidence",
        ),
        Index(
            "ix_goal_criterion_assessment_evidence_assessment_id",
            "assessment_id",
        ),
    )


class GoalCriterionAssessmentEventDB(Base):
    __tablename__ = "goal_criterion_assessment_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goal_criterion_assessments.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    lifecycle_state: Mapped[GoalAssessmentLifecycle | None] = mapped_column(
        Enum(GoalAssessmentLifecycle, name="goal_assessment_event_lifecycle")
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    assessment = relationship("GoalCriterionAssessmentDB", back_populates="events")
    actor = relationship("UserDB")

    __table_args__ = (
        Index(
            "ix_goal_criterion_assessment_events_assessment_created",
            "assessment_id",
            "created_at",
        ),
    )
