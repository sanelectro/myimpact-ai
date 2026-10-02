from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.document import DocumentScopeType, DocumentType


class DocumentChunkDB(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Position in the document. Multiple chunks can share the same heading
    # path, so order is deliberately separate from heading hierarchy.
    chunk_index: Mapped[int] = mapped_column(
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Canonical breadcrumb. An empty list represents content without a
    # document heading hierarchy.
    heading_path: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )

    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"),
        nullable=False,
    )

    scope_type: Mapped[DocumentScopeType] = mapped_column(
        Enum(DocumentScopeType, name="document_scope_type"),
        nullable=False,
    )

    scope_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
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
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
        Index(
            "ix_document_chunks_document_index",
            "document_id",
            "chunk_index",
        ),
    )