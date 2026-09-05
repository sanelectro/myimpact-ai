from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.evidence import EvidenceSourceType, EvidenceStatus


class EvidenceDB(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[EvidenceSourceType] = mapped_column(Enum(EvidenceSourceType, name="evidence_source_type"), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[EvidenceStatus] = mapped_column(Enum(EvidenceStatus, name="evidence_status"), nullable=False, default=EvidenceStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user = relationship("UserDB", back_populates="evidence")
    versions = relationship("EvidenceVersionDB", back_populates="evidence", cascade="all, delete-orphan")
    mappings = relationship("EvidenceMappingDB", back_populates="evidence", cascade="all, delete-orphan")
    impact_assessments = relationship("ImpactAssessmentDB", back_populates="evidence", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_evidence_source", "source_type", "source_id"),)
