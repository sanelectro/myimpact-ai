from sqlalchemy.orm import Session
from datetime import UTC, datetime
from app.db.models.impact_assessment import ImpactAssessmentDB
from app.models.impact_assessment import ImpactType
from app.repositories.base import BaseRepository


class ImpactAssessmentRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)
        
    def get_by_id(
        self,
        assessment_id: str,
    ) -> ImpactAssessmentDB | None:
        return self.session.get(ImpactAssessmentDB, assessment_id)
    
    
    def get_by_evidence_id(
        self,
        evidence_id: str,
    ) -> list[ImpactAssessmentDB]:
        return (
            self.session.query(ImpactAssessmentDB)
            .filter(ImpactAssessmentDB.evidence_id == evidence_id)
            .all()
        )
        
        
    def get_by_goal_id(
        self,
        goal_id: str,
    ) -> list[ImpactAssessmentDB]:
        return (
            self.session.query(ImpactAssessmentDB)
            .filter(ImpactAssessmentDB.goal_id == goal_id)
            .all()
        )
        
    def get_by_evidence_and_goal(
        self,
        evidence_id: str,
        goal_id: str,
    ) -> ImpactAssessmentDB | None:
        return (
            self.session.query(ImpactAssessmentDB)
            .filter(
                ImpactAssessmentDB.evidence_id == evidence_id,
                ImpactAssessmentDB.goal_id == goal_id,
            )
            .first()
        )
        
    
    def create(
        self,
        *,
        assessment_id: str,
        evidence_id: str,
        goal_id: str,
        impact_type: ImpactType,
        impact_summary: str,
        impact_score: float,
        confidence: float,
        assessment_version: int = 1,
    ) -> ImpactAssessmentDB:
        now = datetime.now(UTC)

        assessment = ImpactAssessmentDB(
            id=assessment_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=impact_type,
            impact_summary=impact_summary,
            impact_score=impact_score,
            confidence=confidence,
            assessment_version=assessment_version,
            created_at=now,
            updated_at=now,
        )

        self.session.add(assessment)
        self.session.flush()

        return assessment