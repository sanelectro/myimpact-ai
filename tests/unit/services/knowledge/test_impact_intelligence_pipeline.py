from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.exceptions import ImpactAssessmentEvaluationError
from app.models.document_expectation import DocumentExpectation
from app.models.evidence import EvidenceSourceType
from app.models.goal import Goal
from app.models.impact_assessment import ImpactType
from app.models.impact_intelligence import (
    CareerInsight,
    EvidenceCandidate,
    EvidenceEvaluation,
    EvidenceSupportLevel,
)
from app.services.knowledge.impact_intelligence_pipeline import (
    ImpactIntelligencePipelineService,
)


def make_goal() -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id="goal-1",
        user_id="user-1",
        title="Improve engineering effectiveness",
        description="Improve platform architecture and delivery effectiveness.",
        created_at=now,
        updated_at=now,
    )


def make_expectation(expectation_id: str) -> DocumentExpectation:
    now = datetime.now(UTC)
    return DocumentExpectation(
        id=expectation_id,
        document_id="doc-1",
        category="architecture",
        description="Improve platform architecture",
        evidence_hints=["architecture", "delivery"],
        confidence=0.9,
        created_at=now,
        updated_at=now,
    )


def make_evidence_db(evidence_id: str = "evidence-1"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=evidence_id,
        user_id="user-1",
        source_type=EvidenceSourceType.DOCUMENT,
        source_id="chunk-1",
        title="Architecture improvement",
        description="Improved platform architecture and delivery.",
        source_url=None,
        captured_at=now,
        source_updated_at=None,
        content_hash="hash",
        status="active",
        created_at=now,
        updated_at=now,
    )


def make_assessment_db(evidence_id: str = "evidence-1"):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=f"assessment-{evidence_id}",
        evidence_id=evidence_id,
        goal_id="goal-1",
        impact_type=ImpactType.TECHNICAL,
        impact_summary="Improved platform architecture.",
        impact_score=0.82,
        confidence=0.91,
        assessment_version=1,
        created_at=now,
        updated_at=now,
    )


def make_candidate(expectation_id: str, chunk_id: str) -> EvidenceCandidate:
    now = datetime.now(UTC)
    from app.models.document_chunk_embedding import KnowledgeSearchResult

    result = KnowledgeSearchResult(
        chunk_id=chunk_id,
        document_id="doc-1",
        content="Improved platform architecture and delivery.",
        heading_path=[],
        document_type="role",
        scope_type="user",
        scope_id="user-1",
        metadata={},
        similarity=0.91,
    )
    return EvidenceCandidate(expectation_id=expectation_id, search_result=result)


def make_evaluation(chunk_id: str, supported: bool = True) -> EvidenceEvaluation:
    return EvidenceEvaluation(
        candidate_chunk_id=chunk_id,
        supports_expectation=supported,
        support_level=(
            EvidenceSupportLevel.STRONG if supported else EvidenceSupportLevel.NONE
        ),
        confidence=0.9,
        rationale="The evidence directly describes the expected improvement.",
    )


def make_service():
    return ImpactIntelligencePipelineService(
        discovery_service=Mock(),
        evaluation_service=Mock(),
        persistence_service=Mock(),
        impact_evaluation_service=Mock(),
        impact_assessment_service=Mock(),
        career_insight_service=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_runs_full_pipeline_and_synthesizes_career_insight():
    service = make_service()
    goal = make_goal()
    expectation = make_expectation("expectation-1")
    candidate = make_candidate(expectation.id, "chunk-1")
    evaluation = make_evaluation("chunk-1")

    service.discovery_service.discover = AsyncMock(return_value=[candidate])
    service.evaluation_service.evaluate = AsyncMock(return_value=[evaluation])
    service.persistence_service.persist_evaluation = Mock(
        return_value=(make_evidence_db(), SimpleNamespace(), SimpleNamespace())
    )
    service.impact_evaluation_service.evaluate = AsyncMock(
        return_value=SimpleNamespace(
            impact_type=ImpactType.TECHNICAL,
            impact_summary="Improved platform architecture.",
            impact_score=0.82,
            confidence=0.91,
        )
    )
    service.impact_assessment_service.create_assessment = Mock(
        return_value=make_assessment_db()
    )
    service.career_insight_service.synthesize = AsyncMock(
        return_value=CareerInsight(
            goal_id="goal-1",
            headline="Stronger platform engineering impact",
            summary="Evidence shows architecture impact.",
            impact_types=[ImpactType.TECHNICAL],
            supporting_assessment_ids=["assessment-evidence-1"],
            confidence=0.9,
        )
    )

    result = await service.run(goal, [expectation], user_id="user-1", discovery_limit=3)

    assert result.processed_expectations == 1
    assert result.discovered_candidates == 1
    assert result.evaluated_candidates == 1
    assert result.persisted_evidence_count == 1
    assert result.impact_assessment_count == 1
    assert result.career_insight.goal_id == goal.id
    service.discovery_service.discover.assert_awaited_once_with(
        expectation, limit=3, user_id="user-1"
    )
    service.career_insight_service.synthesize.assert_awaited_once()


@pytest.mark.asyncio
async def test_skips_unsupported_evidence_without_assessment():
    service = make_service()
    candidate = make_candidate("expectation-1", "chunk-1")
    evaluation = make_evaluation("chunk-1", supported=False)

    service.discovery_service.discover = AsyncMock(return_value=[candidate])
    service.evaluation_service.evaluate = AsyncMock(return_value=[evaluation])
    service.persistence_service.persist_evaluation = Mock(return_value=None)

    with pytest.raises(ImpactAssessmentEvaluationError, match="No supported evidence"):
        await service.run(make_goal(), [make_expectation("expectation-1")], user_id="user-1")

    service.impact_evaluation_service.evaluate.assert_not_called()
    service.career_insight_service.synthesize.assert_not_awaited()


@pytest.mark.asyncio
async def test_deduplicates_same_evidence_across_expectations():
    service = make_service()
    expectations = [make_expectation("expectation-1"), make_expectation("expectation-2")]
    candidate_1 = make_candidate("expectation-1", "chunk-1")
    candidate_2 = make_candidate("expectation-2", "chunk-1")
    service.discovery_service.discover = AsyncMock(side_effect=[[candidate_1], [candidate_2]])
    service.evaluation_service.evaluate = AsyncMock(
        side_effect=[[make_evaluation("chunk-1")], [make_evaluation("chunk-1")]]
    )
    service.persistence_service.persist_evaluation = Mock(
        return_value=(make_evidence_db(), SimpleNamespace(), SimpleNamespace())
    )
    service.impact_evaluation_service.evaluate = AsyncMock(
        return_value=SimpleNamespace(
            impact_type=ImpactType.TECHNICAL,
            impact_summary="Improved platform architecture.",
            impact_score=0.8,
            confidence=0.9,
        )
    )
    service.impact_assessment_service.create_assessment = Mock(return_value=make_assessment_db())
    service.career_insight_service.synthesize = AsyncMock(
        return_value=CareerInsight(
            goal_id="goal-1",
            headline="Architecture impact",
            summary="Architecture improved.",
            impact_types=[ImpactType.TECHNICAL],
            supporting_assessment_ids=["assessment-evidence-1"],
            confidence=0.9,
        )
    )

    result = await service.run(make_goal(), expectations, user_id="user-1")

    assert result.persisted_evidence_count == 2
    assert result.impact_assessment_count == 1
    assert service.impact_evaluation_service.evaluate.await_count == 1
    service.impact_assessment_service.create_assessment.assert_called_once()


@pytest.mark.asyncio
async def test_rejects_goal_from_another_user_before_processing():
    service = make_service()
    goal = make_goal().model_copy(update={"user_id": "user-2"})

    with pytest.raises(ImpactAssessmentEvaluationError, match="does not belong"):
        await service.run(goal, [make_expectation("expectation-1")], user_id="user-1")

    service.discovery_service.discover.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_empty_expectations():
    service = make_service()

    with pytest.raises(ImpactAssessmentEvaluationError, match="At least one expectation"):
        await service.run(make_goal(), [], user_id="user-1")

    service.discovery_service.discover.assert_not_called()


@pytest.mark.asyncio
async def test_rejects_invalid_discovery_limit():
    service = make_service()

    with pytest.raises(ValueError, match="discovery_limit"):
        await service.run(
            make_goal(), [make_expectation("expectation-1")], user_id="user-1", discovery_limit=0
        )


@pytest.mark.asyncio
async def test_rejects_evaluation_count_mismatch():
    service = make_service()
    candidate = make_candidate("expectation-1", "chunk-1")
    service.discovery_service.discover = AsyncMock(return_value=[candidate])
    service.evaluation_service.evaluate = AsyncMock(return_value=[])

    with pytest.raises(ImpactAssessmentEvaluationError, match="count does not match"):
        await service.run(make_goal(), [make_expectation("expectation-1")], user_id="user-1")


@pytest.mark.asyncio
async def test_processes_multiple_supported_evidence_items():
    service = make_service()
    expectation = make_expectation("expectation-1")
    candidates = [make_candidate(expectation.id, "chunk-1"), make_candidate(expectation.id, "chunk-2")]
    evaluations = [make_evaluation("chunk-1"), make_evaluation("chunk-2")]
    service.discovery_service.discover = AsyncMock(return_value=candidates)
    service.evaluation_service.evaluate = AsyncMock(return_value=evaluations)
    service.persistence_service.persist_evaluation = Mock(
        side_effect=[
            (make_evidence_db("evidence-1"), SimpleNamespace(), SimpleNamespace()),
            (make_evidence_db("evidence-2"), SimpleNamespace(), SimpleNamespace()),
        ]
    )
    service.impact_evaluation_service.evaluate = AsyncMock(
        side_effect=[
            SimpleNamespace(
                impact_type=ImpactType.TECHNICAL,
                impact_summary="Architecture improved.",
                impact_score=0.8,
                confidence=0.9,
            ),
            SimpleNamespace(
                impact_type=ImpactType.RELIABILITY,
                impact_summary="Reliability improved.",
                impact_score=0.7,
                confidence=0.85,
            ),
        ]
    )
    service.impact_assessment_service.create_assessment = Mock(
        side_effect=[make_assessment_db("evidence-1"), make_assessment_db("evidence-2")]
    )
    service.career_insight_service.synthesize = AsyncMock(
        return_value=CareerInsight(
            goal_id="goal-1",
            headline="Broader engineering impact",
            summary="Architecture and reliability improvements are supported.",
            impact_types=[ImpactType.TECHNICAL, ImpactType.RELIABILITY],
            supporting_assessment_ids=["assessment-evidence-1", "assessment-evidence-2"],
            confidence=0.9,
        )
    )

    result = await service.run(make_goal(), [expectation], user_id="user-1")

    assert result.discovered_candidates == 2
    assert result.evaluated_candidates == 2
    assert result.persisted_evidence_count == 2
    assert result.impact_assessment_count == 2
    assert service.impact_assessment_service.create_assessment.call_count == 2
