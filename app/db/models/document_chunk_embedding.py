from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentChunkEmbeddingDB(Base):
    __tablename__ = "document_chunk_embeddings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    chunk_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # No fixed dimension is declared at the database type level. The model and
    # dimension are stored explicitly so a future embedding model can coexist
    # safely while retrieval filters on the active model/dimension.
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR(),
        nullable=False,
    )

    embedding_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    embedding_dimensions: Mapped[int] = mapped_column(
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    chunk = relationship("DocumentChunkDB")

    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            name="uq_document_chunk_embeddings_chunk_id",
        ),
        Index(
            "ix_document_chunk_embeddings_model_dimensions",
            "embedding_model",
            "embedding_dimensions",
        ),
    )
