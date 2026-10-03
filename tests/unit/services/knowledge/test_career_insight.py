from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.exceptions import ImpactAssessmentEvaluationError
from app.models.goal import Goal
from app.models.impact_assessment import ImpactAssessment, ImpactType
from app.models.llm import LLMResponse
from app.services.knowledge.career_insight import CareerInsightService
from app.services.llm.interface import ILLMService


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


def make_assessment(
    assessment_id: str,
    impact_type: ImpactType,
    summary: str,
) -> ImpactAssessment:
    now = datetime.now(UTC)
    return ImpactAssessment(
        id=assessment_id,
        evidence_id=f"evidence-{assessment_id}",
        goal_id="goal-1",
        impact_type=impact_type,
        impact_summary=summary,
        impact_score=0.8,
        confidence=0.9,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def llm_service() -> AsyncMock:
    return AsyncMock(spec=ILLMService)


@pytest.fixture
def service(llm_service: AsyncMock) -> CareerInsightService:
    return CareerInsightService(llm_service)


async def test_synthesizes_goal_level_career_insight(service, llm_service):
    assessments = [
        make_assessment("assessment-1", ImpactType.TECHNICAL, "Improved platform architecture."),
        make_assessment("assessment-2", ImpactType.RELIABILITY, "Improved service reliability."),
    ]
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"goal_id":"goal-1","headline":"Stronger platform engineering impact",'
            '"summary":"The evidence shows impact across architecture and reliability.",'
            '"impact_types":["technical","reliability"],"supporting_assessment_ids":'
            '["assessment-1","assessment-2"],"confidence":0.91}'
        ),
        model="test-model",
    )

    result = await service.synthesize(make_goal(), assessments)

    assert result.goal_id == "goal-1"
    assert result.impact_types == [ImpactType.TECHNICAL, ImpactType.RELIABILITY]
    assert result.supporting_assessment_ids == ["assessment-1", "assessment-2"]
    assert result.confidence == 0.91
    request = llm_service.generate.await_args.args[0]
    assert "Do not invent outcomes" in request.prompt
    assert "Improve engineering effectiveness" in request.prompt
    assert "assessment-1" in request.prompt


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"goal_id":"goal-1","headline":"x","summary":"x","impact_types":'
        '["unknown"],"supporting_assessment_ids":[],"confidence":0.9}',
        '{"goal_id":"goal-1","headline":"x","summary":"x","impact_types":[],"supporting_assessment_ids":[],"confidence":1.2}',
        '{"goal_id":"goal-1","summary":"x","impact_types":[],"supporting_assessment_ids":[],"confidence":0.9}',
    ],
)
async def test_rejects_invalid_llm_response(service, llm_service, content):
    llm_service.generate.return_value = LLMResponse(content=content)

    with pytest.raises(ImpactAssessmentEvaluationError, match="invalid response"):
        await service.synthesize(make_goal(), [make_assessment("assessment-1", ImpactType.TECHNICAL, "Improved architecture.")])


async def test_wraps_provider_failure(service, llm_service):
    llm_service.generate.side_effect = RuntimeError("provider secret")

    with pytest.raises(ImpactAssessmentEvaluationError, match="provider failed") as error:
        await service.synthesize(make_goal(), [make_assessment("assessment-1", ImpactType.TECHNICAL, "Improved architecture.")])

    assert "provider secret" not in str(error.value)


async def test_rejects_empty_assessments(service, llm_service):
    with pytest.raises(ImpactAssessmentEvaluationError, match="At least one"):
        await service.synthesize(make_goal(), [])

    llm_service.generate.assert_not_awaited()


async def test_rejects_assessment_for_another_goal(service, llm_service):
    assessment = make_assessment("assessment-1", ImpactType.TECHNICAL, "Improved architecture.")
    assessment = assessment.model_copy(update={"goal_id": "goal-2"})

    with pytest.raises(ImpactAssessmentEvaluationError, match="belong to the supplied goal"):
        await service.synthesize(make_goal(), [assessment])

    llm_service.generate.assert_not_awaited()


async def test_rejects_unknown_supporting_assessment(service, llm_service):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"goal_id":"goal-1","headline":"Architecture impact",'
            '"summary":"Improved architecture.","impact_types":["technical"],"'
            'supporting_assessment_ids":["assessment-unknown"],"confidence":0.8}'
        )
    )

    with pytest.raises(ImpactAssessmentEvaluationError, match="unknown assessment"):
        await service.synthesize(
            make_goal(),
            [make_assessment("assessment-1", ImpactType.TECHNICAL, "Improved architecture.")],
        )


async def test_rejects_insight_for_different_goal(service, llm_service):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"goal_id":"goal-2","headline":"Architecture impact",'
            '"summary":"Improved architecture.","impact_types":["technical"],"'
            'supporting_assessment_ids":["assessment-1"],"confidence":0.8}'
        )
    )

    with pytest.raises(ImpactAssessmentEvaluationError, match="different goal"):
        await service.synthesize(
            make_goal(),
            [make_assessment("assessment-1", ImpactType.TECHNICAL, "Improved architecture.")],
        )
