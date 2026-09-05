from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.evidence_mapping import EvidenceMappingDB
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.models.evidence_mapping import EvidenceRelevance
from app.repositories.evidence_mapping import EvidenceMappingRepository
from app.services.base import BaseService


class EvidenceMappingService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = EvidenceMappingRepository(session)

    def create_mapping(
        self,
        *,
        evidence_id: str,
        goal_id: str,
        relevance: EvidenceRelevance,
        confidence: float,
        reason: str | None = None,
    ) -> EvidenceMappingDB:
        existing = self.repository.get_by_evidence_and_goal(
            evidence_id,
            goal_id,
        )

        if existing is not None:
            raise EvidenceMappingAlreadyExistsError(
                "Evidence is already mapped to this goal."
            )

        mapping = self.repository.create(
            mapping_id=str(uuid4()),
            evidence_id=evidence_id,
            goal_id=goal_id,
            relevance=relevance,
            confidence=confidence,
            reason=reason,
        )
        self.commit()
        return mapping

    def get_mapping_by_id(
        self,
        mapping_id: str,
    ) -> EvidenceMappingDB | None:
        return self.repository.get_by_id(mapping_id)

    def get_mappings_by_evidence_id(
        self,
        evidence_id: str,
    ) -> list[EvidenceMappingDB]:
        return self.repository.get_by_evidence_id(evidence_id)

    def get_mappings_by_goal_id(
        self,
        goal_id: str,
    ) -> list[EvidenceMappingDB]:
        return self.repository.get_by_goal_id(goal_id)

    def get_mapping_by_evidence_and_goal(
        self,
        evidence_id: str,
        goal_id: str,
    ) -> EvidenceMappingDB | None:
        return self.repository.get_by_evidence_and_goal(
            evidence_id,
            goal_id,
        )
