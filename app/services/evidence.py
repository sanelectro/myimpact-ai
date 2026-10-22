from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceDB
from app.models.evidence import EvidenceCreate, EvidenceSourceType, EvidenceStatus
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

    def archive_evidence(self, evidence_id: str) -> EvidenceDB:
        evidence = self.repository.get_by_id(evidence_id)
        if evidence is None:
            raise ValueError("Evidence not found")
        if evidence.status != EvidenceStatus.ACTIVE:
            raise ValueError("Only active evidence can be archived")
        now = datetime.now(UTC)
        evidence = self.repository.update(
            evidence,
            {
                "status": EvidenceStatus.ARCHIVED,
                "archived_at": now,
                "updated_at": now,
            },
        )
        self.commit()
        return evidence

    def delete_archived_evidence(self, evidence_id: str) -> None:
        evidence = self.repository.get_by_id(evidence_id)
        if evidence is None:
            raise ValueError("Evidence not found")
        if evidence.status != EvidenceStatus.ARCHIVED:
            raise ValueError("Only archived evidence can be deleted")
        self.repository.delete(evidence)
        self.commit()

    def get_evidence_by_source(
        self,
        source_type: EvidenceSourceType,
        source_id: str | None,
    ) -> EvidenceDB | None:
        return self.repository.get_by_source(source_type, source_id)
