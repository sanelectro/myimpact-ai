from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.impact_assessment import ImpactType


class ImpactAssessmentDB(Base):
    __tablename__ = "impact_assessments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(64), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_id: Mapped[str] = mapped_column(String(64), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True)
    impact_type: Mapped[ImpactType] = mapped_column(Enum(ImpactType, name="impact_type"), nullable=False)
    impact_summary: Mapped[str] = mapped_column(Text, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    assessment_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evidence = relationship("EvidenceDB", back_populates="impact_assessments")
    goal = relationship("GoalDB", back_populates="impact_assessments")
