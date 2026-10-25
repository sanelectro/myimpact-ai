from pydantic import ValidationError

from app.exceptions import MilestoneSuggestionError
from app.models.goal import Goal
from app.models.llm import LLMRequest
from app.models.milestone import MilestoneSuggestion, MilestoneSuggestionsResponse
from app.services.llm.interface import ILLMService


class MilestoneSuggestionService:
    """Generate actionable, goal-specific milestones without persisting them."""

    def __init__(self, llm_service: ILLMService) -> None:
        self.llm_service = llm_service

    @staticmethod
    def build_prompt(goal: Goal) -> str:
        return (
            "Suggest 3 to 5 actionable milestones that help accomplish the supplied goal. "
            "Return only a JSON object with a suggestions array. Each item must contain "
            "title, description, and completion_criteria. Keep each milestone distinct, "
            "sequenced where useful, and specific to the supplied goal. Do not add dates. "
            "Base suggestions only on the goal information; do not invent company context, "
            "resources, results, or commitments. Completion criteria should describe an "
            "observable outcome without inventing a numeric target.\n\n"
            "GOAL:\n"
            f"title: {goal.title}\n"
            f"description: {goal.description or ''}\n"
            f"scope: {goal.scope.value}\n"
            f"start_date: {goal.start_date.isoformat() if goal.start_date else ''}\n"
            f"end_date: {goal.end_date.isoformat() if goal.end_date else ''}\n"
        )

    @staticmethod
    def _normalize_json_response(content: str) -> str:
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        return content

    async def suggest(self, goal: Goal) -> list[MilestoneSuggestion]:
        try:
            response = await self.llm_service.generate(
                LLMRequest(prompt=self.build_prompt(goal)),
            )
        except Exception as exc:
            raise MilestoneSuggestionError(
                "Milestone suggestion provider failed."
            ) from exc

        try:
            result = MilestoneSuggestionsResponse.model_validate_json(
                self._normalize_json_response(response.content),
            )
        except ValidationError as exc:
            raise MilestoneSuggestionError(
                "Milestone suggestion provider returned an invalid response."
            ) from exc

        titles = [suggestion.title.strip().casefold() for suggestion in result.suggestions]
        if len(titles) != len(set(titles)):
            raise MilestoneSuggestionError(
                "Milestone suggestion provider returned duplicate titles."
            )

        return result.suggestions
