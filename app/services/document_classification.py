from pydantic import ValidationError

from app.exceptions import DocumentClassificationError
from app.models.document import DocumentClassification, DocumentType
from app.models.llm import LLMRequest
from app.services.llm.interface import ILLMService


class DocumentClassificationService:
    def __init__(
        self,
        llm_service: ILLMService,
        minimum_confidence: float,
    ) -> None:
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1.")

        self.llm_service = llm_service
        self.minimum_confidence = minimum_confidence

    async def classify(self, content: str) -> DocumentClassification:
        if not content.strip():
            raise DocumentClassificationError(
                "Document content is required for classification."
            )

        supported_types = ", ".join(
            document_type.value for document_type in DocumentType
        )
        request = LLMRequest(
            prompt=(
                "Classify the document content below. Return only a JSON "
                "object with document_type, confidence, and reason. "
                f"document_type must be one of: {supported_types}. "
                "confidence must be a number from 0 to 1.\n\n"
                "DOCUMENT CONTENT:\n"
                f"{content}"
            )
        )

        try:
            response = await self.llm_service.generate(request)
        except Exception as exc:
            raise DocumentClassificationError(
                "Document classification provider failed."
            ) from exc

        try:
            classification = DocumentClassification.model_validate_json(
                response.content
            )
        except ValidationError as exc:
            raise DocumentClassificationError(
                "Document classification returned an invalid response."
            ) from exc

        if classification.confidence < self.minimum_confidence:
            return classification.model_copy(
                update={"document_type": DocumentType.UNKNOWN}
            )

        return classification