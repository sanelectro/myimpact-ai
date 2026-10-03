from datetime import datetime, timezone

from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.models.document_expectation import DocumentExpectation
from app.models.expectation import ExpectationCategory
from app.models.impact_intelligence import (
    EvidenceCandidate,
    EvidenceEvaluation,
    EvidenceSupportLevel,
    ExpectationEvidenceResult,
)


def make_expectation() -> DocumentExpectation:
    now = datetime.now(timezone.utc)
    return DocumentExpectation(
        id="exp-1",
        document_id="doc-1",
        category=ExpectationCategory.TECHNICAL_LEADERSHIP,
        description="Lead technical design and delivery.",
        evidence_hints=["architecture", "design"],
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )


def make_search_result() -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        chunk_id="chunk-1",
        document_id="doc-1",
        content="Led the design of the service architecture.",
        heading_path=["Technical Leadership"],
        document_type="performance_review",
        scope_type="role",
        similarity=0.91,
    )


def test_evidence_candidate_wraps_retrieved_knowledge():
    candidate = EvidenceCandidate(
        expectation_id="exp-1",
        search_result=make_search_result(),
    )

    assert candidate.expectation_id == "exp-1"
    assert candidate.search_result.chunk_id == "chunk-1"
    assert candidate.search_result.similarity == 0.91


def test_evidence_evaluation_validates_confidence_and_support_level():
    evaluation = EvidenceEvaluation(
        candidate_chunk_id="chunk-1",
        supports_expectation=True,
        support_level=EvidenceSupportLevel.STRONG,
        confidence=0.88,
        rationale="The chunk directly describes technical design leadership.",
    )

    assert evaluation.support_level is EvidenceSupportLevel.STRONG
    assert evaluation.supports_expectation is True
    assert evaluation.confidence == 0.88


def test_expectation_evidence_result_combines_expectation_candidates_and_evaluations():
    result = ExpectationEvidenceResult(
        expectation=make_expectation(),
        candidates=[
            EvidenceCandidate(
                expectation_id="exp-1",
                search_result=make_search_result(),
            )
        ],
        evaluations=[
            EvidenceEvaluation(
                candidate_chunk_id="chunk-1",
                supports_expectation=True,
                support_level=EvidenceSupportLevel.MODERATE,
                confidence=0.8,
                rationale="The chunk supports the expectation.",
            )
        ],
    )

    assert result.expectation.id == "exp-1"
    assert len(result.candidates) == 1
    assert len(result.evaluations) == 1
