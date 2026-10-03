from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.routes.document import (
    _validate_upload,
    get_document_classification_service,
    get_document_chunking_service,
    get_document_expectation_extraction_service,
    get_document_service,
)
from app.db.session import get_db
from app.exceptions import (
    DocumentClassificationError,
    DocumentChunkingError,
    DocumentExpectationExtractionError,
    DocumentExtractionError,
)
from app.models.api_v1_knowledge import (
    KnowledgeDocumentResponse,
    KnowledgeResult,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
)
from app.models.document import DocumentScopeType, DocumentType
from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.repositories.document_chunk_embedding import DocumentChunkEmbeddingRepository
from app.services.document import DocumentService
from app.services.embedding.factory import create_embedding_service
from app.services.knowledge.semantic_retrieval import SemanticRetrievalService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def get_retrieval_service(
    db: Annotated[Session, Depends(get_db)],
) -> SemanticRetrievalService:
    return SemanticRetrievalService(
        repository=DocumentChunkEmbeddingRepository(db),
        embedding_service=create_embedding_service(),
    )


def _to_document_response(document) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=document.id,
        file_name=document.file_name,
        content_type=document.content_type,
        document_type=document.document_type,
        scope_type=document.scope_type,
        scope_id=document.scope_id,
        status=document.status,
        classification_type=document.classification_type,
        classification_confidence=document.classification_confidence,
        created_at=document.created_at.isoformat(),
        updated_at=document.updated_at.isoformat(),
    )


def _require_document_owner(document, user_id: str) -> None:
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if document.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")


@router.post("/documents", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_knowledge_document(
    user_id: Annotated[str, Form()],
    document_type: Annotated[DocumentType, Form()],
    file: Annotated[UploadFile, File()],
    service: Annotated[DocumentService, Depends(get_document_service)],
    scope_type: Annotated[DocumentScopeType, Form()] = DocumentScopeType.EMPLOYEE,
    scope_id: Annotated[str | None, Form()] = None,
) -> KnowledgeDocumentResponse:
    content = await file.read()
    _validate_upload(file.filename, file.content_type, content)

    document = service.upload_document(
        user_id=user_id,
        document_type=document_type,
        scope_type=scope_type,
        scope_id=scope_id,
        file_name=file.filename,
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )

    try:
        document = await service.process_document(document.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        DocumentExtractionError,
        DocumentClassificationError,
        DocumentExpectationExtractionError,
        DocumentChunkingError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return _to_document_response(document)


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
def list_knowledge_documents(
    user_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> list[KnowledgeDocumentResponse]:
    return [_to_document_response(document) for document in service.get_documents_by_user_id(user_id)]


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentResponse)
def get_knowledge_document(
    document_id: str,
    user_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> KnowledgeDocumentResponse:
    document = service.get_document_by_id(document_id)
    _require_document_owner(document, user_id)
    return _to_document_response(document)


@router.post("/documents/{document_id}/reprocess", response_model=KnowledgeDocumentResponse)
async def reprocess_knowledge_document(
    document_id: str,
    user_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> KnowledgeDocumentResponse:
    existing = service.get_document_by_id(document_id)
    _require_document_owner(existing, user_id)

    try:
        document = await service.process_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        DocumentExtractionError,
        DocumentClassificationError,
        DocumentExpectationExtractionError,
        DocumentChunkingError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return _to_document_response(document)


@router.post("/retrieve", response_model=KnowledgeRetrievalResponse)
async def retrieve_knowledge(
    request: KnowledgeRetrievalRequest,
    service: Annotated[SemanticRetrievalService, Depends(get_retrieval_service)],
) -> KnowledgeRetrievalResponse:
    try:
        results: list[KnowledgeSearchResult] = await service.retrieve(
            request.query,
            limit=request.limit,
            document_id=request.document_id,
            user_id=request.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return KnowledgeRetrievalResponse(
        results=[
            KnowledgeResult(
                document_id=result.document_id,
                content=result.content,
                heading_path=result.heading_path,
                document_type=result.document_type,
                scope_type=result.scope_type,
                scope_id=result.scope_id,
                metadata=result.metadata,
            )
            for result in results
        ]
    )
