from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceDB
from app.models.evidence import EvidenceCreate, EvidenceSourceType
from app.repositories.evidence import EvidenceRepository
from app.services.base import BaseService


class EvidenceService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = EvidenceRepository(session)

    def create_evidence(self, evidence_data: EvidenceCreate) -> EvidenceDB:
        evidence = self.repository.create(
            evidence_id=str(uuid4()),
            user_id=evidence_data.user_id,
            source_type=evidence_data.source_type,
            title=evidence_data.title,
            description=evidence_data.description,
            source_id=evidence_data.source_id,
            source_url=evidence_data.source_url,
            captured_at=evidence_data.captured_at,
            source_updated_at=evidence_data.source_updated_at,
            content_hash=evidence_data.content_hash,
        )
        self.commit()
        return evidence

    def get_evidence_by_id(self, evidence_id: str) -> EvidenceDB | None:
        return self.repository.get_by_id(evidence_id)

    def get_evidence_by_user_id(self, user_id: str) -> list[EvidenceDB]:
        return self.repository.get_by_user_id(user_id)

    def get_evidence_by_source(
        self,
        source_type: EvidenceSourceType,
        source_id: str | None,
    ) -> EvidenceDB | None:
        return self.repository.get_by_source(source_type, source_id)
