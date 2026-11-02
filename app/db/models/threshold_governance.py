from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.threshold_governance import (
    ThresholdDecision,
    ThresholdOperator,
    ThresholdSetStatus,
)


class MetricDefinitionDB(Base):
    __tablename__ = "metric_definitions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    metric_id: Mapped[str] = mapped_column(String(128), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "metric_id",
            "definition_version",
            name="uq_metric_definition_version",
        ),
        Index("ix_metric_definitions_metric_active", "metric_id", "active"),
    )


class ThresholdSetDB(Base):
    __tablename__ = "threshold_sets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ThresholdSetStatus] = mapped_column(
        SQLEnum(ThresholdSetStatus, native_enum=False, create_constraint=False),
        nullable=False,
        default=ThresholdSetStatus.DRAFT,
    )
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    model_configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    evaluation_code_version: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    proposal_rationale: Mapped[str] = mapped_column(Text, nullable=False)

    items = relationship(
        "ThresholdItemDB",
        back_populates="threshold_set",
        cascade="all, delete-orphan",
        order_by="ThresholdItemDB.metric_id",
    )
    approvals = relationship(
        "ThresholdApprovalDB",
        back_populates="threshold_set",
        cascade="all, delete-orphan",
        order_by="ThresholdApprovalDB.decided_at",
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "dataset_version",
            "version",
            name="uq_threshold_set_version",
        ),
        CheckConstraint("version > 0", name="ck_threshold_set_version_positive"),
        CheckConstraint(
            "length(trim(proposal_rationale)) > 0",
            name="ck_threshold_set_rationale",
        ),
    )


class ThresholdItemDB(Base):
    __tablename__ = "threshold_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    threshold_set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("threshold_sets.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_definition_version: Mapped[str] = mapped_column(String(100), nullable=False)
    operator: Mapped[ThresholdOperator] = mapped_column(
        SQLEnum(ThresholdOperator, native_enum=False, create_constraint=False),
        nullable=False,
    )
    threshold_value: Mapped[float] = mapped_column(Numeric(8, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(nullable=False, default=True)

    threshold_set = relationship("ThresholdSetDB", back_populates="items")

    __table_args__ = (
        UniqueConstraint(
            "threshold_set_id",
            "metric_id",
            name="uq_threshold_item_metric",
        ),
        CheckConstraint(
            "threshold_value >= 0 AND threshold_value <= 1",
            name="ck_threshold_item_ratio_range",
        ),
        CheckConstraint(
            "length(trim(rationale)) > 0",
            name="ck_threshold_item_rationale",
        ),
    )


class ThresholdApprovalDB(Base):
    __tablename__ = "threshold_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    threshold_set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("threshold_sets.id", ondelete="RESTRICT"), nullable=False
    )
    threshold_set_version: Mapped[int] = mapped_column(nullable=False)
    decision: Mapped[ThresholdDecision] = mapped_column(
        SQLEnum(ThresholdDecision, native_enum=False, create_constraint=False),
        nullable=False,
    )
    approver_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    policy_reference: Mapped[str | None] = mapped_column(String(200))

    threshold_set = relationship("ThresholdSetDB", back_populates="approvals")

    __table_args__ = (
        CheckConstraint(
            "length(trim(rationale)) > 0",
            name="ck_threshold_approval_rationale",
        ),
    )


class ThresholdAuditEventDB(Base):
    __tablename__ = "threshold_audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    threshold_set_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("threshold_sets.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ix_threshold_audit_set_created",
            "threshold_set_id",
            "created_at",
            "id",
        ),
    )
