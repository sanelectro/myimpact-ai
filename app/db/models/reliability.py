from datetime import datetime

from sqlalchemy import (
    DateTime,
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


class AIModelDB(Base):
    __tablename__ = "mst_ai_models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_identifier: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReliabilityExperimentDB(Base):
    __tablename__ = "reliability_experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    case_selection: Mapped[list] = mapped_column(JSON, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    ai_model_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("mst_ai_models.id", ondelete="RESTRICT")
    )
    model_configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    retrieval_configuration_version: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    source_snapshot_id: Mapped[str | None] = mapped_column(String(200))
    evaluation_code_version: Mapped[str] = mapped_column(String(200), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(100), nullable=False)
    repetitions_per_case: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts = relationship(
        "ReliabilityAttemptDB",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ReliabilityAttemptDB.case_id, ReliabilityAttemptDB.sequence",
    )
    comparisons = relationship(
        "ReliabilityComparisonDB",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ReliabilityComparisonDB.case_id",
    )
    reports = relationship(
        "ReliabilityReportDB",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ReliabilityReportDB.generated_at",
    )

    __table_args__ = (
        Index(
            "ix_reliability_experiments_dataset_status",
            "dataset_id",
            "dataset_version",
            "status",
        ),
    )


class ReliabilityAttemptDB(Base):
    __tablename__ = "reliability_attempts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("reliability_experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(200), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    ai_model_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("mst_ai_models.id", ondelete="RESTRICT")
    )
    retrieval_configuration_version: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    source_snapshot_id: Mapped[str | None] = mapped_column(String(200))
    input_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_output: Mapped[dict | None] = mapped_column(JSON)
    normalized_output: Mapped[dict | None] = mapped_column(JSON)
    schema_valid: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    experiment = relationship("ReliabilityExperimentDB", back_populates="attempts")

    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "case_id",
            "sequence",
            name="uq_reliability_attempt_sequence",
        ),
        Index(
            "ix_reliability_attempts_experiment_case",
            "experiment_id",
            "case_id",
            "sequence",
        ),
    )


class ReliabilityComparisonDB(Base):
    __tablename__ = "reliability_comparisons"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("reliability_experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(200), nullable=False)
    attempt_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    exact_output_consistent: Mapped[bool | None] = mapped_column()
    difference_categories: Mapped[list] = mapped_column(JSON, nullable=False)
    differences: Mapped[list] = mapped_column(JSON, nullable=False)
    exclusion_reasons: Mapped[list] = mapped_column(JSON, nullable=False)
    comparison_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    experiment = relationship(
        "ReliabilityExperimentDB", back_populates="comparisons"
    )

    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "case_id",
            name="uq_reliability_comparison_case",
        ),
    )


class ReliabilityReportDB(Base):
    __tablename__ = "reliability_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("reliability_experiments.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_version: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_definition_versions: Mapped[dict] = mapped_column(JSON, nullable=False)
    threshold_set_id: Mapped[str | None] = mapped_column(String(64))
    threshold_set_version: Mapped[int | None] = mapped_column(Integer)
    threshold_result: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    coverage: Mapped[dict] = mapped_column(JSON, nullable=False)
    divergent_case_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    experiment = relationship("ReliabilityExperimentDB", back_populates="reports")

    __table_args__ = (
        Index(
            "ix_reliability_reports_experiment_generated",
            "experiment_id",
            "generated_at",
        ),
    )
