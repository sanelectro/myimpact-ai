from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.expectation import DocumentExpectationDB
from app.models.expectation import ExpectationCategory
from app.repositories.base import BaseRepository


class DocumentExpectationRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, expectation_id: str) -> DocumentExpectationDB | None:
        return self.session.get(DocumentExpectationDB, expectation_id)

    def get_by_document_id(
        self,
        document_id: str,
    ) -> list[DocumentExpectationDB]:
        return (
            self.session.query(DocumentExpectationDB)
            .filter(DocumentExpectationDB.document_id == document_id)
            .order_by(DocumentExpectationDB.created_at)
            .all()
        )

    def get_by_document_and_category(
        self,
        document_id: str,
        category: ExpectationCategory,
    ) -> list[DocumentExpectationDB]:
        return (
            self.session.query(DocumentExpectationDB)
            .filter(
                DocumentExpectationDB.document_id == document_id,
                DocumentExpectationDB.category == category,
            )
            .order_by(DocumentExpectationDB.created_at)
            .all()
        )

    def create(
        self,
        *,
        expectation_id: str,
        document_id: str,
        category: ExpectationCategory,
        description: str,
        evidence_hints: list[str],
        source_page: int | None = None,
        source_section: str | None = None,
        source_text_span: str | None = None,
        confidence: float,
    ) -> DocumentExpectationDB:
        now = datetime.now(UTC)

        expectation = DocumentExpectationDB(
            id=expectation_id,
            document_id=document_id,
            category=category,
            description=description,
            evidence_hints=evidence_hints,
            source_page=source_page,
            source_section=source_section,
            source_text_span=source_text_span,
            confidence=confidence,
            created_at=now,
            updated_at=now,
        )

        self.session.add(expectation)
        self.session.flush()

        return expectation

    def delete_by_document_id(self, document_id: str) -> int:
        expectations = (
            self.session.query(DocumentExpectationDB)
            .filter(DocumentExpectationDB.document_id == document_id)
            .all()
        )

        for expectation in expectations:
            self.session.delete(expectation)

        self.session.flush()
        return len(expectations)
