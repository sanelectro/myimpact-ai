from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoalDefinitionProposalHeadDB(Base):
    __tablename__ = "goal_definition_proposal_heads"

    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), primary_key=True
    )
    base_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    relationship_revision: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["base_version_id", "goal_id"],
            ["goal_versions.id", "goal_versions.goal_id"],
            name="fk_goal_proposal_head_base",
        ),
        ForeignKeyConstraint(
            ["proposal_version_id", "goal_id"],
            ["goal_versions.id", "goal_versions.goal_id"],
            name="fk_goal_proposal_head_version",
        ),
        CheckConstraint("revision > 0", name="ck_goal_proposal_head_revision"),
        CheckConstraint(
            "relationship_revision >= 0",
            name="ck_goal_proposal_head_relationship_revision",
        ),
    )


class GoalCommandReceiptDB(Base):
    __tablename__ = "goal_command_receipts"

    actor_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    command_kind: Mapped[str] = mapped_column(String(40), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    goal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    result_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    result_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["result_version_id", "goal_id"],
            ["goal_versions.id", "goal_versions.goal_id"],
            name="fk_goal_command_receipt_result",
        ),
        CheckConstraint(
            "command_kind = 'PREPARE_DEFINITION'", name="ck_goal_command_receipt_kind"
        ),
        CheckConstraint(
            "length(trim(idempotency_key)) > 0", name="ck_goal_command_receipt_key"
        ),
        CheckConstraint("result_revision >= 0", name="ck_goal_command_receipt_revision"),
        CheckConstraint("outcome IN ('CREATED', 'NO_CHANGE')", name="ck_goal_command_receipt_outcome"),
    )
