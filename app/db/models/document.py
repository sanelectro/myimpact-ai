from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.document import DocumentScopeType, DocumentStatus, DocumentType


class DocumentDB(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # user_id is the uploader/owner. Applicability is determined by scope.
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

    scope_type: Mapped[DocumentScopeType] = mapped_column(
        Enum(DocumentScopeType, name="document_scope_type"),
        nullable=False,
        default=DocumentScopeType.EMPLOYEE,
    )

    scope_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
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

    # The extracted/normalized Markdown is kept in file storage.
    extracted_content_path: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    classification_type: Mapped[DocumentType | None] = mapped_column(
        Enum(DocumentType, name="document_type"),
        nullable=True,
    )

    classification_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    classification_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    classification_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

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

    __table_args__ = (
        Index(
            "ix_documents_scope",
            "scope_type",
            "scope_id",
        ),
    )
