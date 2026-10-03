from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.exceptions import ImpactAssessmentEvaluationError
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.goal import Goal
from app.models.impact_assessment import ImpactType
from app.models.llm import LLMResponse
from app.services.knowledge.impact_assessment import ImpactAssessmentEvaluationService
from app.services.llm.interface import ILLMService


def make_evidence(description: str | None = "Led architecture improvements that reduced deployment friction.") -> Evidence:
    now = datetime.now(UTC)
    return Evidence(
        id="evidence-1",
        user_id="user-1",
        source_type=EvidenceSourceType.DOCUMENT,
        title="Architecture improvement",
        description=description,
        captured_at=now,
        created_at=now,
        updated_at=now,
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


@pytest.fixture
def llm_service() -> AsyncMock:
    return AsyncMock(spec=ILLMService)


@pytest.fixture
def service(llm_service: AsyncMock) -> ImpactAssessmentEvaluationService:
    return ImpactAssessmentEvaluationService(llm_service)


async def test_evaluates_evidence_impact(service, llm_service):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"impact_type":"technical","impact_summary":"Improved platform architecture.",'
            '"impact_score":0.82,"confidence":0.91}'
        ),
        model="test-model",
    )

    result = await service.evaluate(make_evidence(), make_goal())

    assert result.impact_type is ImpactType.TECHNICAL
    assert result.impact_score == 0.82
    assert result.confidence == 0.91
    request = llm_service.generate.await_args.args[0]
    assert "Do not infer impact" in request.prompt
    assert "Improve engineering effectiveness" in request.prompt
    assert "Architecture improvement" in request.prompt


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"impact_type":"unknown","impact_summary":"x","impact_score":0.8,"confidence":0.9}',
        '{"impact_type":"technical","impact_summary":"x","impact_score":1.2,"confidence":0.9}',
        '{"impact_type":"technical","impact_summary":"x","impact_score":0.8,"confidence":-0.1}',
        '{"impact_type":"technical","impact_score":0.8,"confidence":0.9}',
    ],
)
async def test_rejects_invalid_llm_response(service, llm_service, content):
    llm_service.generate.return_value = LLMResponse(content=content)

    with pytest.raises(ImpactAssessmentEvaluationError, match="invalid response"):
        await service.evaluate(make_evidence(), make_goal())


async def test_wraps_provider_failure(service, llm_service):
    llm_service.generate.side_effect = RuntimeError("provider secret")

    with pytest.raises(ImpactAssessmentEvaluationError, match="provider failed") as error:
        await service.evaluate(make_evidence(), make_goal())

    assert "provider secret" not in str(error.value)


async def test_rejects_evidence_without_description(service, llm_service):
    with pytest.raises(ImpactAssessmentEvaluationError, match="description"):
        await service.evaluate(make_evidence(None), make_goal())

    llm_service.generate.assert_not_awaited()


async def test_allows_goal_without_description(service, llm_service):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"impact_type":"technical","impact_summary":"Improved architecture.",'
            '"impact_score":0.7,"confidence":0.8}'
        )
    )
    goal = make_goal().model_copy(update={"description": None})

    result = await service.evaluate(make_evidence(), goal)

    assert result.impact_type is ImpactType.TECHNICAL
    request = llm_service.generate.await_args.args[0]
    assert "description: " in request.prompt
