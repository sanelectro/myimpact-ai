from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.exceptions import EvidenceEvaluationError
from app.models.document_expectation import DocumentExpectation
from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.models.expectation import ExpectationCategory
from app.models.impact_intelligence import (
    EvidenceCandidate,
    EvidenceSupportLevel,
)
from app.models.llm import LLMResponse
from app.services.knowledge.evidence_evaluation import EvidenceEvaluationService
from app.services.llm.interface import ILLMService


def make_expectation() -> DocumentExpectation:
    now = datetime.now(UTC)
    return DocumentExpectation(
        id="expectation-1",
        document_id="document-1",
        category=ExpectationCategory.ARCHITECTURE,
        description="Drive architecture decisions across the platform",
        evidence_hints=["architecture reviews"],
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )


def make_candidate(expectation_id: str = "expectation-1") -> EvidenceCandidate:
    return EvidenceCandidate(
        expectation_id=expectation_id,
        search_result=KnowledgeSearchResult(
            chunk_id="chunk-1",
            document_id="document-1",
            content="Led architecture decisions for the platform.",
            heading_path=["Architecture"],
            document_type="role",
            scope_type="employee",
            scope_id="user-1",
            metadata={},
            similarity=0.91,
        ),
    )


@pytest.fixture
def llm_service() -> AsyncMock:
    return AsyncMock(spec=ILLMService)


@pytest.fixture
def service(llm_service: AsyncMock) -> EvidenceEvaluationService:
    return EvidenceEvaluationService(llm_service)


async def test_evaluates_candidate(service, llm_service):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"candidate_chunk_id":"chunk-1","supports_expectation":true,'
            '"support_level":"strong","confidence":0.93,'
            '"rationale":"The evidence explicitly describes architecture decisions."}'
        ),
        model="test-model",
    )

    result = await service.evaluate_candidate(make_expectation(), make_candidate())

    assert result.candidate_chunk_id == "chunk-1"
    assert result.supports_expectation is True
    assert result.support_level == EvidenceSupportLevel.STRONG
    assert result.confidence == 0.93
    request = llm_service.generate.await_args.args[0]
    assert "Do not infer achievement from semantic similarity alone" in request.prompt
    assert "Drive architecture decisions across the platform" in request.prompt


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"candidate_chunk_id":"chunk-1","supports_expectation":true,'
        '"support_level":"unknown","confidence":0.9,"rationale":"x"}',
        '{"candidate_chunk_id":"chunk-1","supports_expectation":true,'
        '"support_level":"strong","confidence":1.2,"rationale":"x"}',
        '{"candidate_chunk_id":"chunk-1","supports_expectation":true,'
        '"support_level":"strong","confidence":0.9}',
    ],
)
async def test_rejects_invalid_llm_response(service, llm_service, content):
    llm_service.generate.return_value = LLMResponse(content=content)

    with pytest.raises(EvidenceEvaluationError, match="invalid response"):
        await service.evaluate_candidate(make_expectation(), make_candidate())


async def test_wraps_provider_failure(service, llm_service):
    llm_service.generate.side_effect = RuntimeError("provider secret")

    with pytest.raises(EvidenceEvaluationError, match="provider failed") as error:
        await service.evaluate_candidate(make_expectation(), make_candidate())

    assert "provider secret" not in str(error.value)


async def test_rejects_candidate_for_different_expectation(service, llm_service):
    with pytest.raises(EvidenceEvaluationError, match="does not belong"):
        await service.evaluate_candidate(
            make_expectation(), make_candidate("other-expectation")
        )

    llm_service.generate.assert_not_awaited()


async def test_rejects_evaluation_for_wrong_chunk(service, llm_service):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"candidate_chunk_id":"chunk-2","supports_expectation":true,'
            '"support_level":"moderate","confidence":0.8,"rationale":"Supported."}'
        )
    )

    with pytest.raises(EvidenceEvaluationError, match="unexpected candidate chunk"):
        await service.evaluate_candidate(make_expectation(), make_candidate())


async def test_evaluate_returns_evaluations_for_all_candidates(service, llm_service):
    llm_service.generate.side_effect = [
        LLMResponse(
            content=(
                '{"candidate_chunk_id":"chunk-1","supports_expectation":true,'
                '"support_level":"strong","confidence":0.9,"rationale":"Supported."}'
            )
        ),
        LLMResponse(
            content=(
                '{"candidate_chunk_id":"chunk-2","supports_expectation":false,'
                '"support_level":"none","confidence":0.88,"rationale":"Unrelated."}'
            )
        ),
    ]
    second = make_candidate()
    second.search_result = second.search_result.model_copy(update={"chunk_id": "chunk-2"})

    result = await service.evaluate(make_expectation(), [make_candidate(), second])

    assert [item.candidate_chunk_id for item in result] == ["chunk-1", "chunk-2"]
    assert result[1].support_level == EvidenceSupportLevel.NONE
    assert llm_service.generate.await_count == 2
