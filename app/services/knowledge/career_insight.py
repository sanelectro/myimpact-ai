from pydantic import ValidationError

from app.exceptions import ImpactAssessmentEvaluationError
from app.models.goal import Goal
from app.models.impact_assessment import ImpactAssessment
from app.models.impact_intelligence import CareerInsight
from app.models.llm import LLMRequest
from app.services.llm.interface import ILLMService


class CareerInsightService:
    """Synthesize persisted impact assessments into a goal-level career insight."""

    def __init__(self, llm_service: ILLMService) -> None:
        self.llm_service = llm_service

    @staticmethod
    def build_prompt(
        goal: Goal,
        assessments: list[ImpactAssessment],
    ) -> str:
        assessment_lines = "\n".join(
            (
                f"id: {assessment.id}\n"
                f"impact_type: {assessment.impact_type.value}\n"
                f"impact_summary: {assessment.impact_summary}\n"
                f"impact_score: {assessment.impact_score}\n"
                f"confidence: {assessment.confidence}"
            )
            for assessment in assessments
        )
        return (
            "Synthesize the supplied impact assessments into one concise career insight "
            "for the supplied goal. Return only a JSON object with goal_id, headline, summary, "
            "impact_types, supporting_assessment_ids, and confidence. "
            "goal_id must exactly match the supplied goal id. "
            "impact_types must contain only impact types present in the supplied assessments. "
            "supporting_assessment_ids must contain only supplied assessment IDs. "
            "confidence must be a number from 0 to 1. "
            "Base the insight only on the supplied goal and assessments. "
            "Do not invent outcomes, metrics, achievements, themes, or gaps that are not "
            "supported by the assessments. Do not use assessment score as a new performance "
            "metric; use it only as context when synthesizing the supplied assessments. "
            "Keep the headline and summary concise.\n\n"
            "GOAL:\n"
            f"id: {goal.id}\n"
            f"title: {goal.title}\n"
            f"description: {goal.description or ''}\n\n"
            "IMPACT ASSESSMENTS:\n"
            f"{assessment_lines}\n"
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

    async def synthesize(
        self,
        goal: Goal,
        assessments: list[ImpactAssessment],
    ) -> CareerInsight:
        if not assessments:
            raise ImpactAssessmentEvaluationError(
                "At least one impact assessment is required for career insight."
            )

        invalid = [
            assessment.id
            for assessment in assessments
            if assessment.goal_id != goal.id
        ]
        if invalid:
            raise ImpactAssessmentEvaluationError(
                "All impact assessments must belong to the supplied goal."
            )

        request = LLMRequest(prompt=self.build_prompt(goal, assessments))

        try:
            response = await self.llm_service.generate(request)
        except Exception as exc:
            raise ImpactAssessmentEvaluationError(
                "Career insight provider failed."
            ) from exc

        normalized_content = self._normalize_json_response(response.content)

        try:
            insight = CareerInsight.model_validate_json(normalized_content)
        except ValidationError as exc:
            raise ImpactAssessmentEvaluationError(
                "Career insight returned an invalid response."
            ) from exc

        if insight.goal_id != goal.id:
            raise ImpactAssessmentEvaluationError(
                "Career insight returned a different goal."
            )

        supplied_ids = {assessment.id for assessment in assessments}
        if not set(insight.supporting_assessment_ids).issubset(supplied_ids):
            raise ImpactAssessmentEvaluationError(
                "Career insight referenced an unknown assessment."
            )

        return insight
