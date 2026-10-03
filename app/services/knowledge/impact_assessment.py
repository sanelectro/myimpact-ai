from pydantic import ValidationError

from app.exceptions import ImpactAssessmentEvaluationError
from app.models.evidence import Evidence
from app.models.goal import Goal
from app.models.impact_assessment import ImpactType
from app.models.impact_intelligence import ImpactAssessmentEvaluation
from app.models.llm import LLMRequest
from app.services.llm.interface import ILLMService


class ImpactAssessmentEvaluationService:
    """Evaluate the impact of persisted evidence against a user goal."""

    def __init__(self, llm_service: ILLMService) -> None:
        self.llm_service = llm_service

    @staticmethod
    def build_prompt(evidence: Evidence, goal: Goal) -> str:
        impact_types = ", ".join(item.value for item in ImpactType)
        return (
            "Assess the impact represented by the evidence against the goal. "
            "Return only a JSON object with impact_type, impact_summary, "
            "impact_score, and confidence. "
            f"impact_type must be one of: {impact_types}. "
            "impact_score and confidence must be numbers from 0 to 1. "
            "Base the assessment only on the supplied goal and evidence. "
            "Do not infer impact from the source type, semantic similarity, or "
            "assumed outcomes that are not stated in the evidence. "
            "The summary must describe the supported impact without inventing metrics. "
            "Keep the summary concise and evidence-grounded.\n\n"
            "GOAL:\n"
            f"title: {goal.title}\n"
            f"description: {goal.description or ''}\n\n"
            "EVIDENCE:\n"
            f"title: {evidence.title}\n"
            f"description: {evidence.description or ''}\n"
            f"source_type: {evidence.source_type.value}\n"
        )

    async def evaluate(
        self,
        evidence: Evidence,
        goal: Goal,
    ) -> ImpactAssessmentEvaluation:
        if not evidence.description or not evidence.description.strip():
            raise ImpactAssessmentEvaluationError(
                "Evidence must contain a description before impact assessment."
            )

        request = LLMRequest(prompt=self.build_prompt(evidence, goal))

        try:
            response = await self.llm_service.generate(request)
        except Exception as exc:
            raise ImpactAssessmentEvaluationError(
                "Impact assessment provider failed."
            ) from exc

        try:
            evaluation = ImpactAssessmentEvaluation.model_validate_json(response.content)
        except ValidationError as exc:
            raise ImpactAssessmentEvaluationError(
                "Impact assessment returned an invalid response."
            ) from exc

        return evaluation
