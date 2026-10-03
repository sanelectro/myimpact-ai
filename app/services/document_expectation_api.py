from sqlalchemy.orm import Session

from app.repositories.expectation import DocumentExpectationRepository


class DocumentExpectationApiService:
    """Read-only application service for product-facing expectation APIs."""

    def __init__(self, session: Session):
        self.repository = DocumentExpectationRepository(session)

    def get_by_document_id(self, document_id: str):
        return self.repository.get_by_document_id(document_id)
