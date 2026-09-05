from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.evidence_version import EvidenceVersionDB
from app.repositories.evidence_version import EvidenceVersionRepository
from app.services.base import BaseService


class EvidenceVersionService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = EvidenceVersionRepository(session)

    def create_version(
        self,
        *,
        evidence_id: str,
        content: str,
        content_hash: str,
        captured_at: datetime,
        source_updated_at: datetime | None = None,
    ) -> EvidenceVersionDB:
        existing_versions = self.repository.get_by_evidence_id(evidence_id)
        next_version = (
            max(version.version for version in existing_versions) + 1
            if existing_versions
            else 1
        )

        version_record = self.repository.create(
            version_id=str(uuid4()),
            evidence_id=evidence_id,
            version=next_version,
            content=content,
            content_hash=content_hash,
            captured_at=captured_at,
            source_updated_at=source_updated_at,
        )
        self.commit()
        return version_record

    def get_version_by_id(
        self,
        version_id: str,
    ) -> EvidenceVersionDB | None:
        return self.repository.get_by_id(version_id)

    def get_versions_by_evidence_id(
        self,
        evidence_id: str,
    ) -> list[EvidenceVersionDB]:
        return self.repository.get_by_evidence_id(evidence_id)

    def get_version(
        self,
        evidence_id: str,
        version: int,
    ) -> EvidenceVersionDB | None:
        return self.repository.get_by_evidence_id_and_version(
            evidence_id,
            version,
        )
