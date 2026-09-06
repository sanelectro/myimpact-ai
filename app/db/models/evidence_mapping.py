from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.evidence_mapping import EvidenceRelevance


class EvidenceMappingDB(Base):
    __tablename__ = "evidence_mappings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(64), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_id: Mapped[str] = mapped_column(String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True)
    relevance: Mapped[EvidenceRelevance] = mapped_column(Enum(EvidenceRelevance, name="evidence_relevance"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evidence = relationship("EvidenceDB", back_populates="mappings")
    goal = relationship("GoalDB", back_populates="evidence_mappings")

    __table_args__ = (UniqueConstraint("evidence_id", "goal_id", name="uq_evidence_goal_mapping"),)
