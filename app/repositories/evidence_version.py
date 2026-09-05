from sqlalchemy.orm import Session

from app.db.models.evidence_version import EvidenceVersionDB
from app.repositories.base import BaseRepository
from datetime import UTC, datetime

class EvidenceVersionRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)
        
    def get_by_id(self, version_id: str) -> EvidenceVersionDB | None:
        return self.session.get(EvidenceVersionDB, version_id)
    
    def get_by_evidence_id(self, evidence_id: str) -> list[EvidenceVersionDB]:
        return (
            self.session.query(EvidenceVersionDB)
            .filter(EvidenceVersionDB.evidence_id == evidence_id)
            .order_by(EvidenceVersionDB.version)
            .all()
        )
        
    def get_by_evidence_id_and_version(
        self,
        evidence_id: str,
        version: int,
    ) -> EvidenceVersionDB | None:
        return (
            self.session.query(EvidenceVersionDB)
            .filter(
                EvidenceVersionDB.evidence_id == evidence_id,
                EvidenceVersionDB.version == version,
            )
            .first()
        )
        
    def create(
        self,
        *,
        version_id: str,
        evidence_id: str,
        version: int,
        content: str,
        content_hash: str,
        captured_at: datetime,
        source_updated_at: datetime | None = None,
    ) -> EvidenceVersionDB:
        version_record = EvidenceVersionDB(
            id=version_id,
            evidence_id=evidence_id,
            version=version,
            content=content,
            content_hash=content_hash,
            source_updated_at=source_updated_at,
            captured_at=captured_at,
            created_at=datetime.now(UTC),
        )

        self.session.add(version_record)
        self.session.flush()

        return version_record