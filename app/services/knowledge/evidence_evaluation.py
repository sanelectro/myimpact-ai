from pydantic import ValidationError

from app.exceptions import EvidenceEvaluationError
from app.models.document_expectation import DocumentExpectation
from app.models.impact_intelligence import (
    EvidenceCandidate,
    EvidenceEvaluation,
    EvidenceSupportLevel,
)
from app.models.llm import LLMRequest
from app.services.llm.interface import ILLMService


class EvidenceEvaluationService:
    """Evaluate whether retrieved evidence supports an expectation."""

    def __init__(self, llm_service: ILLMService) -> None:
        self.llm_service = llm_service

    @staticmethod
    def build_prompt(
        expectation: DocumentExpectation,
        candidate: EvidenceCandidate,
    ) -> str:
        return (
            "Evaluate whether the evidence supports the stated expectation. "
            "Return only a JSON object with candidate_chunk_id, "
            "supports_expectation, support_level, confidence, and rationale. "
            "support_level must be one of: none, weak, moderate, strong. "
            "confidence must be a number from 0 to 1. "
            "Do not infer achievement from semantic similarity alone. "
            "Evaluate only the content of the candidate against the expectation. "
            "If the evidence is insufficient or unrelated, use supports_expectation=false "
            "and support_level=none. Keep the rationale concise and grounded in the evidence.\n\n"
            "EXPECTATION:\n"
            f"{expectation.description}\n\n"
            "EVIDENCE CANDIDATE:\n"
            f"chunk_id: {candidate.search_result.chunk_id}\n"
            f"content: {candidate.search_result.content}"
        )

    async def evaluate_candidate(
        self,
        expectation: DocumentExpectation,
        candidate: EvidenceCandidate,
    ) -> EvidenceEvaluation:
        if candidate.expectation_id != expectation.id:
            raise EvidenceEvaluationError(
                "Evidence candidate does not belong to the supplied expectation."
            )

        request = LLMRequest(prompt=self.build_prompt(expectation, candidate))

        try:
            response = await self.llm_service.generate(request)
        except Exception as exc:
            raise EvidenceEvaluationError(
                "Evidence evaluation provider failed."
            ) from exc

        try:
            evaluation = EvidenceEvaluation.model_validate_json(response.content)
        except ValidationError as exc:
            raise EvidenceEvaluationError(
                "Evidence evaluation returned an invalid response."
            ) from exc

        if evaluation.candidate_chunk_id != candidate.search_result.chunk_id:
            raise EvidenceEvaluationError(
                "Evidence evaluation returned an unexpected candidate chunk."
            )

        return evaluation

    async def evaluate(
        self,
        expectation: DocumentExpectation,
        candidates: list[EvidenceCandidate],
    ) -> list[EvidenceEvaluation]:
        evaluations: list[EvidenceEvaluation] = []
        for candidate in candidates:
            evaluations.append(
                await self.evaluate_candidate(expectation, candidate)
            )
        return evaluations
