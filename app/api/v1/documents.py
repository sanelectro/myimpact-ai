import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.routes.document import (
    MAX_DOCUMENT_SIZE_BYTES,
    _validate_upload,
    get_document_service,
)
from app.db.session import get_db
from app.exceptions import (
    DocumentClassificationError,
    DocumentChunkingError,
    DocumentExpectationExtractionError,
    DocumentExtractionError,
)
from app.models.document import Document, DocumentScopeType, DocumentType
from app.services.document import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.post("/import", response_model=Document, status_code=status.HTTP_201_CREATED)
async def import_document(
    user_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    service: Annotated[DocumentService, Depends(get_document_service)],
    scope_type: Annotated[DocumentScopeType, Form()] = DocumentScopeType.EMPLOYEE,
    scope_id: Annotated[str | None, Form()] = None,
    source: Annotated[str, Form()] = "file_import",
) -> Document:
    content = await file.read(MAX_DOCUMENT_SIZE_BYTES + 1)
    _validate_upload(file.filename, file.content_type, content)
    try:
        document = service.upload_document(
            user_id=user_id,
            document_type=DocumentType.UNKNOWN,
            scope_type=scope_type,
            scope_id=scope_id,
            file_name=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            content=content,
            source=source,
        )
        document = await service.process_document(document.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        DocumentExtractionError,
        DocumentClassificationError,
        DocumentExpectationExtractionError,
        DocumentChunkingError,
    ) as exc:
        logger.exception("Document processing failed for document %s", document.id)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return Document.model_validate(document, from_attributes=True)
