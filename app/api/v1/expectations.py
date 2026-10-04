from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.routes.document import get_document_service
from app.api.v1.knowledge import _require_document_owner
from app.db.session import get_db
from app.models.document_expectation import DocumentExpectation
from app.services.document import DocumentService
from app.services.document_expectation_api import DocumentExpectationApiService

router = APIRouter(prefix="/knowledge/documents", tags=["expectations"])


def get_expectation_service(
    db: Annotated[Session, Depends(get_db)],
) -> DocumentExpectationApiService:
    return DocumentExpectationApiService(db)


@router.get("/{document_id}/expectations", response_model=list[DocumentExpectation])
def list_document_expectations(
    document_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    document_service: Annotated[DocumentService, Depends(get_document_service)],
    expectation_service: Annotated[DocumentExpectationApiService, Depends(get_expectation_service)],
) -> list[DocumentExpectation]:
    document = document_service.get_document_by_id(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _require_document_owner(document, user_id)
    return [
        DocumentExpectation.model_validate(expectation, from_attributes=True)
        for expectation in expectation_service.get_by_document_id(document_id)
    ]
