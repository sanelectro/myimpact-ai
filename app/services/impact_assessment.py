from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.impact_assessment import ImpactAssessmentDB
from app.models.impact_assessment import ImpactType
from app.repositories.impact_assessment import ImpactAssessmentRepository
from app.services.base import BaseService


class ImpactAssessmentService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = ImpactAssessmentRepository(session)

    def create_assessment(
        self,
        *,
        evidence_id: str,
        goal_id: str,
        impact_type: ImpactType,
        impact_summary: str,
        impact_score: float,
        confidence: float,
        assessment_version: int | None = None,
    ) -> ImpactAssessmentDB:
        if assessment_version is None:
            existing = self.repository.get_by_evidence_id(evidence_id)
            matching = [
                assessment
                for assessment in existing
                if assessment.goal_id == goal_id
            ]
            assessment_version = (
                max(
                    assessment.assessment_version
                    for assessment in matching
                ) + 1
                if matching
                else 1
            )

        assessment = self.repository.create(
            assessment_id=str(uuid4()),
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=impact_type,
            impact_summary=impact_summary,
            impact_score=impact_score,
            confidence=confidence,
            assessment_version=assessment_version,
        )
        self.commit()
        return assessment

    def get_assessment_by_id(
        self,
        assessment_id: str,
    ) -> ImpactAssessmentDB | None:
        return self.repository.get_by_id(assessment_id)

    def get_assessments_by_evidence_id(
        self,
        evidence_id: str,
    ) -> list[ImpactAssessmentDB]:
        return self.repository.get_by_evidence_id(evidence_id)

    def get_assessments_by_goal_id(
        self,
        goal_id: str,
    ) -> list[ImpactAssessmentDB]:
        return self.repository.get_by_goal_id(goal_id)

    def get_assessment_by_evidence_and_goal(
        self,
        evidence_id: str,
        goal_id: str,
    ) -> ImpactAssessmentDB | None:
        return self.repository.get_by_evidence_and_goal(
            evidence_id,
            goal_id,
        )
