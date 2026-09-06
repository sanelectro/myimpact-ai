from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.evidence_mapping import EvidenceMappingDB
from app.models.evidence_mapping import EvidenceRelevance
from app.repositories.base import BaseRepository


class EvidenceMappingRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, mapping_id: str) -> EvidenceMappingDB | None:
        return self.session.get(EvidenceMappingDB, mapping_id)
    
    def get_by_evidence_id(
        self,
        evidence_id: str,
    ) -> list[EvidenceMappingDB]:
        return (
            self.session.query(EvidenceMappingDB)
            .filter(EvidenceMappingDB.evidence_id == evidence_id)
            .all()
        )
        
    def get_by_goal_id(
        self,
        goal_id: str,
    ) -> list[EvidenceMappingDB]:
        return (
            self.session.query(EvidenceMappingDB)
            .filter(EvidenceMappingDB.goal_id == goal_id)
            .all()
        )
        
        
    def get_by_evidence_and_goal(
        self,
        evidence_id: str,
        goal_id: str,
    ) -> EvidenceMappingDB | None:
        return (
            self.session.query(EvidenceMappingDB)
            .filter(
                EvidenceMappingDB.evidence_id == evidence_id,
                EvidenceMappingDB.goal_id == goal_id,
            )
            .first()
        )
        
    def create(
        self,
        *,
        mapping_id: str,
        evidence_id: str,
        goal_id: str,
        relevance: EvidenceRelevance,
        confidence: float,
        reason: str | None = None,
    ) -> EvidenceMappingDB:
        now = datetime.now(UTC)

        mapping = EvidenceMappingDB(
            id=mapping_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            relevance=relevance,
            reason=reason,
            confidence=confidence,
            created_at=now,
            updated_at=now,
        )

        self.session.add(mapping)
        self.session.flush()

        return mapping