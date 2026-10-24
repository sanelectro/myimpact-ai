from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.evidence_approval import EvidenceApprovalStatus


class EvidenceApprovalDB(Base):
    __tablename__ = "evidence_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mapping_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evidence_mappings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[EvidenceApprovalStatus] = mapped_column(
        Enum(EvidenceApprovalStatus, name="evidence_approval_status"),
        nullable=False,
        default=EvidenceApprovalStatus.PENDING,
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL")
    )
    manager_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    mapping = relationship("EvidenceMappingDB")
    reviewed_by = relationship("UserDB")
