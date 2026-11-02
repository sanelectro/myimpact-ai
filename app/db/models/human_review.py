from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    JSON,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.human_review import M66CaseReviewStatus, M66DatasetReviewStatus


class ReviewBatchDB(Base):
    __tablename__ = "review_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    review_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DUAL_ADJUDICATED"
    )
    status: Mapped[M66DatasetReviewStatus] = mapped_column(
        SQLEnum(M66DatasetReviewStatus, native_enum=False, create_constraint=False),
        nullable=False,
        default=M66DatasetReviewStatus.DRAFT_UNREVIEWED,
    )
    expected_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    started_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    cases = relationship(
        "ReviewCaseDB",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ReviewCaseDB.case_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "dataset_version",
            name="uq_review_batch_dataset_version",
        ),
        CheckConstraint("expected_case_count > 0", name="ck_batch_case_count_positive"),
        CheckConstraint(
            "review_mode IN ('SINGLE_REVIEWER', 'DUAL_ADJUDICATED')",
            name="ck_review_batch_mode",
        ),
        Index("ix_review_batches_dataset_status", "dataset_id", "status"),
    )


class ReviewCaseDB(Base):
    __tablename__ = "review_cases"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("review_batches.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[M66CaseReviewStatus] = mapped_column(
        SQLEnum(M66CaseReviewStatus, native_enum=False, create_constraint=False),
        nullable=False,
    )

    batch = relationship("ReviewBatchDB", back_populates="cases")
    assignments = relationship(
        "ReviewAssignmentDB",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="ReviewAssignmentDB.slot",
    )
    reviews = relationship(
        "ReviewDB",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="ReviewDB.submitted_at",
    )
    adjudications = relationship(
        "AdjudicationDB",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="AdjudicationDB.adjudicated_at",
    )

    __table_args__ = (
        UniqueConstraint("batch_id", "case_id", name="uq_review_case"),
        Index("ix_review_cases_batch_status", "batch_id", "status"),
    )


class ReviewAssignmentDB(Base):
    __tablename__ = "review_assignments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("review_cases.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case = relationship("ReviewCaseDB", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint(
            "case_record_id",
            "reviewer_user_id",
            name="uq_review_assignment_reviewer",
        ),
        UniqueConstraint("case_record_id", "slot", name="uq_review_assignment_slot"),
        CheckConstraint("slot IN (1, 2)", name="ck_review_assignment_slot"),
    )


class ReviewDB(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("review_cases.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewer_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_review_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("reviews.id", ondelete="RESTRICT")
    )

    case = relationship("ReviewCaseDB", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint(
            "case_record_id",
            "reviewer_user_id",
            name="uq_review_case_reviewer",
        ),
        CheckConstraint("length(trim(rationale)) > 0", name="ck_review_rationale"),
        Index("ix_reviews_case_submitted", "case_record_id", "submitted_at"),
    )


class AdjudicationDB(Base):
    __tablename__ = "adjudications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("review_cases.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    review_1_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=False
    )
    review_2_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("reviews.id", ondelete="RESTRICT"), nullable=False
    )
    adjudicator_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    final_label: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    adjudicated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case = relationship("ReviewCaseDB", back_populates="adjudications")

    __table_args__ = (
        UniqueConstraint("case_record_id", name="uq_adjudication_case"),
        CheckConstraint("review_1_id <> review_2_id", name="ck_adjudication_distinct_reviews"),
        CheckConstraint(
            "length(trim(rationale)) > 0",
            name="ck_adjudication_rationale",
        ),
    )


class ReviewAuditEventDB(Base):
    __tablename__ = "review_audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("review_batches.id", ondelete="CASCADE"), nullable=False
    )
    case_record_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("review_cases.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict] = mapped_column("details_json", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_review_audit_batch_created", "batch_id", "created_at", "id"),
    )
