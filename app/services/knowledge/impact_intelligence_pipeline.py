from dataclasses import dataclass

from app.exceptions import ImpactAssessmentEvaluationError
from app.models.document_expectation import DocumentExpectation
from app.models.goal import Goal
from app.models.impact_assessment import ImpactAssessment
from app.models.impact_intelligence import CareerInsight
from app.services.impact_assessment import ImpactAssessmentService
from app.services.knowledge.career_insight import CareerInsightService
from app.services.knowledge.evidence_discovery import EvidenceDiscoveryService
from app.services.knowledge.evidence_evaluation import EvidenceEvaluationService
from app.services.knowledge.evidence_persistence import EvidencePersistenceService
from app.services.knowledge.impact_assessment import ImpactAssessmentEvaluationService


@dataclass(frozen=True)
class ImpactIntelligencePipelineResult:
    """Transient result of one end-to-end impact intelligence run."""

    career_insight: CareerInsight
    processed_expectations: int
    discovered_candidates: int
    evaluated_candidates: int
    persisted_evidence_count: int
    impact_assessment_count: int


class ImpactIntelligencePipelineService:
    """Orchestrate the M4 impact intelligence stages without new persistence."""

    def __init__(
        self,
        discovery_service: EvidenceDiscoveryService,
        evaluation_service: EvidenceEvaluationService,
        persistence_service: EvidencePersistenceService,
        impact_evaluation_service: ImpactAssessmentEvaluationService,
        impact_assessment_service: ImpactAssessmentService,
        career_insight_service: CareerInsightService,
    ) -> None:
        self.discovery_service = discovery_service
        self.evaluation_service = evaluation_service
        self.persistence_service = persistence_service
        self.impact_evaluation_service = impact_evaluation_service
        self.impact_assessment_service = impact_assessment_service
        self.career_insight_service = career_insight_service

    async def run(
        self,
        goal: Goal,
        expectations: list[DocumentExpectation],
        *,
        user_id: str,
        discovery_limit: int = 5,
    ) -> ImpactIntelligencePipelineResult:
        if goal.user_id != user_id:
            raise ImpactAssessmentEvaluationError(
                "Goal does not belong to the supplied user."
            )
        if not expectations:
            raise ImpactAssessmentEvaluationError(
                "At least one expectation is required for impact intelligence."
            )
        if discovery_limit < 1:
            raise ValueError("discovery_limit must be at least 1")

        discovered_candidates = 0
        evaluated_candidates = 0
        persisted_evidence_count = 0
        assessments_by_evidence: dict[str, ImpactAssessment] = {}

        for expectation in expectations:
            candidates = await self.discovery_service.discover(
                expectation,
                limit=discovery_limit,
                user_id=user_id,
            )
            discovered_candidates += len(candidates)

            evaluations = await self.evaluation_service.evaluate(
                expectation,
                candidates,
            )
            evaluated_candidates += len(evaluations)

            if len(evaluations) != len(candidates):
                raise ImpactAssessmentEvaluationError(
                    "Evidence evaluation count does not match candidate count."
                )

            for candidate, evaluation in zip(candidates, evaluations, strict=True):
                persisted = self.persistence_service.persist_evaluation(
                    expectation,
                    candidate,
                    evaluation,
                    user_id=user_id,
                    goal_id=goal.id,
                )
                if persisted is None:
                    continue

                evidence_db, _, _ = persisted
                persisted_evidence_count += 1

                # The same evidence can support multiple expectations. Assess its
                # impact only once for the same goal during this pipeline run.
                if evidence_db.id in assessments_by_evidence:
                    continue

                evidence = self._to_evidence_model(evidence_db)
                impact_evaluation = await self.impact_evaluation_service.evaluate(
                    evidence,
                    goal,
                )
                assessment_db = self.impact_assessment_service.create_assessment(
                    evidence_id=evidence.id,
                    goal_id=goal.id,
                    impact_type=impact_evaluation.impact_type,
                    impact_summary=impact_evaluation.impact_summary,
                    impact_score=impact_evaluation.impact_score,
                    confidence=impact_evaluation.confidence,
                )
                assessments_by_evidence[evidence.id] = self._to_impact_assessment_model(
                    assessment_db
                )

        assessments = list(assessments_by_evidence.values())
        if not assessments:
            raise ImpactAssessmentEvaluationError(
                "No supported evidence was found for impact intelligence."
            )

        career_insight = await self.career_insight_service.synthesize(
            goal,
            assessments,
        )

        return ImpactIntelligencePipelineResult(
            career_insight=career_insight,
            processed_expectations=len(expectations),
            discovered_candidates=discovered_candidates,
            evaluated_candidates=evaluated_candidates,
            persisted_evidence_count=persisted_evidence_count,
            impact_assessment_count=len(assessments),
        )

    @staticmethod
    def _to_evidence_model(evidence_db):
        from app.models.evidence import Evidence

        return Evidence.model_validate(evidence_db, from_attributes=True)

    @staticmethod
    def _to_impact_assessment_model(assessment_db) -> ImpactAssessment:
        return ImpactAssessment(
            id=assessment_db.id,
            evidence_id=assessment_db.evidence_id,
            goal_id=assessment_db.goal_id,
            impact_type=assessment_db.impact_type,
            impact_summary=assessment_db.impact_summary,
            impact_score=assessment_db.impact_score,
            confidence=assessment_db.confidence,
            assessment_version=assessment_db.assessment_version,
            created_at=assessment_db.created_at,
            updated_at=assessment_db.updated_at,
        )
