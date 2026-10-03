from pydantic import ValidationError

from app.exceptions import DocumentExpectationExtractionError
from app.models.expectation import ExpectationExtractionResult
from app.models.llm import LLMRequest
from app.services.llm.interface import ILLMService


class DocumentExpectationExtractionService:
    def __init__(self, llm_service: ILLMService) -> None:
        self.llm_service = llm_service

    async def extract(
        self,
        content: str,
    ) -> ExpectationExtractionResult:
        if not content.strip():
            raise DocumentExpectationExtractionError(
                "Document content is required for expectation extraction."
            )

        request = LLMRequest(
            prompt=(
                "Extract the expectations expressed in the document. "
                "Return only a JSON object with an expectations array. "
                "Each expectation must contain category, description, "
                "evidence_hints, source_reference, and confidence. "
                "category must be one of: delivery, technical_leadership, "
                "architecture, mentoring, innovation, collaboration, "
                "operational_excellence, business_domain_impact. "
                "confidence must be a number from 0 to 1. "
                "Do not claim that an expectation was achieved. "
                "Extract only what the document states or clearly implies "
                "as an expectation. Preserve useful source references such "
                "as page, section, or text span when available. "
                "If there are no meaningful expectations, return an empty "
                "expectations array.\n\n"
                "DOCUMENT CONTENT:\n"
                f"{content}"
            )
        )

        try:
            response = await self.llm_service.generate(request)
        except Exception as exc:
            raise DocumentExpectationExtractionError(
                "Document expectation extraction provider failed."
            ) from exc

        try:
            return ExpectationExtractionResult.model_validate_json(
                response.content
            )
        except ValidationError as exc:
            raise DocumentExpectationExtractionError(
                "Document expectation extraction returned an invalid response."
            ) from exc
