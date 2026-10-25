from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.exceptions import MilestoneSuggestionError
from app.models.goal import Goal, GoalScope
from app.models.llm import LLMResponse
from app.services.knowledge.milestone_suggestion import MilestoneSuggestionService
from app.services.llm.interface import ILLMService


def make_goal() -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id="goal-1",
        user_id="user-1",
        title="Improve service reliability",
        description="Reduce deployment risk and improve service availability.",
        scope=GoalScope.TEAM,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def llm_service() -> AsyncMock:
    return AsyncMock(spec=ILLMService)


@pytest.fixture
def service(llm_service: AsyncMock) -> MilestoneSuggestionService:
    return MilestoneSuggestionService(llm_service)


async def test_generates_valid_goal_specific_milestones(service, llm_service):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '```json\n{"suggestions":[{"title":"Review deployment risks",'
            '"description":"Identify the main reliability risks in the deployment flow.",'
            '"completion_criteria":"A prioritized risk list is reviewed by the team."}]}\n```'
        ),
        model="test-model",
    )

    suggestions = await service.suggest(make_goal())

    assert len(suggestions) == 1
    assert suggestions[0].title == "Review deployment risks"
    request = llm_service.generate.await_args.args[0]
    assert "Improve service reliability" in request.prompt
    assert "do not invent company context" in request.prompt.lower()


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"suggestions":[]}',
        '{"suggestions":[{"title":"Review risks","description":" ","completion_criteria":"Done"}]}',
        '{"suggestions":[{"title":"Same","description":"First","completion_criteria":"Done"},'
        '{"title":" same ","description":"Second","completion_criteria":"Done"}]}',
    ],
)
async def test_rejects_invalid_or_duplicate_suggestions(service, llm_service, content):
    llm_service.generate.return_value = LLMResponse(content=content)

    with pytest.raises(MilestoneSuggestionError):
        await service.suggest(make_goal())


async def test_wraps_provider_failure_without_exposing_provider_details(service, llm_service):
    llm_service.generate.side_effect = RuntimeError("provider secret")

    with pytest.raises(MilestoneSuggestionError, match="provider failed") as error:
        await service.suggest(make_goal())

    assert "provider secret" not in str(error.value)
