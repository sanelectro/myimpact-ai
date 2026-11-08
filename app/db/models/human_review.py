from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
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
from app.models.human_review import M66CaseReviewStatus, M66DatasetReviewStatus


class BenchmarkDatasetVersionDB(Base):
    __tablename__ = "b_mst_dataset_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)

    cases = relationship(
        "BenchmarkCaseVersionDB",
        back_populates="dataset_version_record",
        cascade="all, delete-orphan",
        order_by="BenchmarkCaseVersionDB.case_id",
    )

    __table_args__ = (
        UniqueConstraint("dataset_id", "dataset_version", name="uq_b_dataset_version"),
        CheckConstraint("case_count > 0", name="ck_b_dataset_case_count"),
        Index("ix_b_dataset_versions_status", "status"),
    )


class BenchmarkCaseVersionDB(Base):
    __tablename__ = "b_mst_case_versions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("b_mst_dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    case_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    label_options: Mapped[list] = mapped_column(JSON, nullable=False)
    dimensions: Mapped[list] = mapped_column(JSON, nullable=False)
    polarity: Mapped[str | None] = mapped_column(String(32))
    label_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)

    dataset_version_record = relationship(
        "BenchmarkDatasetVersionDB", back_populates="cases"
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "dataset_version", "case_id", name="uq_b_case_version"
        ),
        Index("ix_b_case_versions_category", "category"),
    )


class BenchmarkCategoryDB(Base):
    __tablename__ = "b_mst_review_categories"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BenchmarkLabelDB(Base):
    __tablename__ = "b_mst_review_labels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("b_mst_review_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    polarity: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("category_id", "label", name="uq_b_review_label"),
    )


class BenchmarkDimensionDB(Base):
    __tablename__ = "b_mst_review_dimensions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BenchmarkReviewProposalDB(Base):
    __tablename__ = "b_review_reference_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_version_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("b_mst_case_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_document: Mapped[str] = mapped_column(String(255), nullable=False)
    source_dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    proposed_label: Mapped[str] = mapped_column(String(64), nullable=False)
    provisional_expected_label: Mapped[str | None] = mapped_column(String(64))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(32))
    evidence_mapping_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    review_flags: Mapped[list] = mapped_column(JSON, nullable=False)
    requires_owner_attention: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "case_version_id",
            "source_document",
            name="uq_b_review_proposal_case_source",
        ),
        CheckConstraint(
            "status IN ('PROPOSED', 'NEEDS_OWNER_REVIEW', 'APPROVED', 'REJECTED')",
            name="ck_b_review_proposal_status",
        ),
        Index(
            "ix_b_review_proposals_status_attention",
            "status",
            "requires_owner_attention",
        ),
    )


class ReviewBatchDB(Base):
    __tablename__ = "b_review_batches"

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(String(64))

    cases = relationship(
        "ReviewCaseDB",
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ReviewCaseDB.case_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "dataset_version", name="uq_b_review_batch_dataset_version"
        ),
        CheckConstraint(
            "expected_case_count > 0", name="ck_b_batch_case_count_positive"
        ),
        CheckConstraint(
            "review_mode IN ('SINGLE_REVIEWER', 'DUAL_ADJUDICATED')",
            name="ck_b_review_batch_mode",
        ),
        Index("ix_b_review_batches_dataset_status", "dataset_id", "status"),
    )


class ReviewCaseDB(Base):
    __tablename__ = "b_review_cases"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("b_review_batches.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    case_version_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("b_mst_case_versions.id", ondelete="RESTRICT")
    )
    category: Mapped[str | None] = mapped_column(String(100))
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
        UniqueConstraint("batch_id", "case_id", name="uq_b_review_case"),
        Index("ix_b_review_cases_batch_status", "batch_id", "status"),
    )


class ReviewAssignmentDB(Base):
    __tablename__ = "b_review_assignments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("b_review_cases.id", ondelete="CASCADE"), nullable=False
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
            name="uq_b_review_assignment_reviewer",
        ),
        UniqueConstraint("case_record_id", "slot", name="uq_b_review_assignment_slot"),
        CheckConstraint("slot IN (1, 2)", name="ck_b_review_assignment_slot"),
    )


class ReviewDB(Base):
    __tablename__ = "b_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("b_review_cases.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    case_version_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("b_mst_case_versions.id", ondelete="RESTRICT")
    )
    reviewer_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    review_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="BLIND")
    ai_attempt_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("reliability_attempts.id", ondelete="RESTRICT")
    )
    reference_proposal_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("b_review_reference_proposals.id", ondelete="RESTRICT"),
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column()
    context_notes: Mapped[str | None] = mapped_column(Text)
    evidence_findings: Mapped[list | None] = mapped_column(JSON)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_review_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("b_reviews.id", ondelete="RESTRICT")
    )

    case = relationship("ReviewCaseDB", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint(
            "case_record_id",
            "reviewer_user_id",
            "review_stage",
            name="uq_b_review_case_reviewer_stage",
        ),
        CheckConstraint(
            "review_stage IN ('BLIND', 'POST_AI', 'PROPOSAL_ASSISTED')",
            name="ck_b_review_stage",
        ),
        CheckConstraint(
            "review_stage <> 'POST_AI' OR ai_attempt_id IS NOT NULL",
            name="ck_b_post_ai_attempt_required",
        ),
        CheckConstraint(
            "(review_stage = 'PROPOSAL_ASSISTED' AND reference_proposal_id IS NOT NULL) "
            "OR (review_stage <> 'PROPOSAL_ASSISTED' AND reference_proposal_id IS NULL)",
            name="ck_b_review_proposal_reference_required",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="ck_b_review_confidence",
        ),
        CheckConstraint("length(trim(rationale)) > 0", name="ck_b_review_rationale"),
        Index(
            "ix_b_reviews_case_stage_submitted",
            "case_record_id",
            "review_stage",
            "submitted_at",
        ),
    )


class AdjudicationDB(Base):
    __tablename__ = "b_adjudications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("b_review_cases.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    review_1_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("b_reviews.id", ondelete="RESTRICT"), nullable=False
    )
    review_2_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("b_reviews.id", ondelete="RESTRICT"), nullable=False
    )
    adjudicator_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    final_label: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    adjudicated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    case = relationship("ReviewCaseDB", back_populates="adjudications")

    __table_args__ = (
        UniqueConstraint("case_record_id", name="uq_b_adjudication_case"),
        CheckConstraint(
            "review_1_id <> review_2_id", name="ck_b_adjudication_distinct_reviews"
        ),
        CheckConstraint(
            "length(trim(rationale)) > 0", name="ck_b_adjudication_rationale"
        ),
    )


class ReviewAuditEventDB(Base):
    __tablename__ = "b_review_audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("b_review_batches.id", ondelete="CASCADE"), nullable=False
    )
    case_record_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("b_review_cases.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict] = mapped_column("details_json", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_b_review_audit_batch_created", "batch_id", "created_at", "id"),
    )


class HumanAIComparisonDB(Base):
    __tablename__ = "b_human_ai_comparisons"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_record_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("b_review_cases.id", ondelete="CASCADE"), nullable=False
    )
    case_version_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("b_mst_case_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    blind_review_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("b_reviews.id", ondelete="RESTRICT"), nullable=False
    )
    post_ai_review_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("b_reviews.id", ondelete="RESTRICT")
    )
    ai_attempt_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("reliability_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    agreement: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comparison_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "blind_review_id", "ai_attempt_id", name="uq_b_human_ai_blind_attempt"
        ),
        CheckConstraint(
            "post_ai_review_id IS NULL OR post_ai_review_id <> blind_review_id",
            name="ck_b_human_ai_distinct_reviews",
        ),
        Index("ix_b_human_ai_case_created", "case_record_id", "created_at"),
    )
