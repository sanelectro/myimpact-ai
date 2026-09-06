from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.document import DocumentStatus, DocumentType


class DocumentDB(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"),
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
    )

    extracted_text: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str | None] = mapped_column(String(500))

    effective_start: Mapped[date | None] = mapped_column(Date)
    effective_end: Mapped[date | None] = mapped_column(Date)

    content_hash: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
    )

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    user = relationship("UserDB")
