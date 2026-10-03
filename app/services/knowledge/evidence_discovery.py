from app.models.document_expectation import DocumentExpectation
from app.models.impact_intelligence import EvidenceCandidate
from app.services.knowledge.semantic_retrieval import SemanticRetrievalService


class EvidenceDiscoveryService:
    """Discover knowledge chunks that may provide evidence for an expectation."""

    def __init__(self, retrieval_service: SemanticRetrievalService) -> None:
        self.retrieval_service = retrieval_service

    @staticmethod
    def build_query(expectation: DocumentExpectation) -> str:
        """Build a deterministic retrieval query from an expectation."""
        parts = [expectation.description.strip()]
        parts.extend(hint.strip() for hint in expectation.evidence_hints if hint.strip())
        return " ".join(parts)

    async def discover(
        self,
        expectation: DocumentExpectation,
        *,
        limit: int = 5,
        user_id: str | None = None,
    ) -> list[EvidenceCandidate]:
        query = self.build_query(expectation)
        results = await self.retrieval_service.retrieve(
            query,
            limit=limit,
            document_id=expectation.document_id,
            user_id=user_id,
        )

        return [
            EvidenceCandidate(
                expectation_id=expectation.id,
                search_result=result,
            )
            for result in results
        ]
