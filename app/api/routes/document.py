from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document, DocumentType
from app.services.document import DocumentService
from app.storage.interface import FileStorage
from app.storage.local import LocalFileStorage

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024

ALLOWED_DOCUMENT_TYPES = {
    ".pdf": {
        "application/pdf",
        "application/octet-stream",
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}


def get_document_storage() -> FileStorage:
    return LocalFileStorage("storage/documents")


def get_document_service(
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[FileStorage, Depends(get_document_storage)],
) -> DocumentService:
    return DocumentService(
        db,
        storage=storage,
    )


def _validate_upload(
    file_name: str | None,
    content_type: str | None,
    content: bytes,
) -> None:
    if not file_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A file name is required.",
        )

    extension = Path(file_name).suffix.lower()

    if extension not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported.",
        )

    allowed_content_types = ALLOWED_DOCUMENT_TYPES[extension]

    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content type does not match the supported document type.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if len(content) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The uploaded file exceeds the 10 MB size limit.",
        )


@router.post(
    "",
    response_model=Document,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    user_id: Annotated[str, Form()],
    document_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File()],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Document:
    content = file.file.read()

    _validate_upload(
        file.filename,
        file.content_type,
        content,
    )

    document = service.upload_document(
        user_id=user_id,
        document_type=document_type,
        file_name=file.filename,
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )

    return Document.model_validate(
        document,
        from_attributes=True,
    )


@router.get(
    "/user/{user_id}/type/{document_type}",
    response_model=list[Document],
)
def get_documents_by_user_and_type(
    user_id: str,
    document_type: DocumentType,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> list[Document]:
    documents = service.get_documents_by_user_and_type(
        user_id,
        document_type,
    )

    return [
        Document.model_validate(
            document,
            from_attributes=True,
        )
        for document in documents
    ]


@router.get(
    "/user/{user_id}",
    response_model=list[Document],
)
def get_documents_by_user_id(
    user_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> list[Document]:
    documents = service.get_documents_by_user_id(user_id)

    return [
        Document.model_validate(
            document,
            from_attributes=True,
        )
        for document in documents
    ]


@router.get(
    "/{document_id}",
    response_model=Document,
)
def get_document_by_id(
    document_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Document:
    document = service.get_document_by_id(document_id)

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return Document.model_validate(
        document,
        from_attributes=True,
    )
