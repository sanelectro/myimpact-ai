from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.expectation import ExpectationCategory


class DocumentExpectationDB(Base):
    __tablename__ = "document_expectations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[ExpectationCategory] = mapped_column(
        Enum(ExpectationCategory, name="expectation_category"),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    evidence_hints: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )

    source_page: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    source_section: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    source_text_span: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    document = relationship("DocumentDB")

    __table_args__ = (
        Index(
            "ix_document_expectations_document_category",
            "document_id",
            "category",
        ),
    )
