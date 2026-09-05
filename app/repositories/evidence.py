from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceDB
from app.models.evidence import EvidenceSourceType, EvidenceStatus
from app.repositories.base import BaseRepository


class EvidenceRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, evidence_id: str) -> EvidenceDB | None:
        return self.session.get(EvidenceDB, evidence_id)
    
    def get_by_user_id(self, user_id: str) -> list[EvidenceDB]:
        return (
            self.session.query(EvidenceDB)
            .filter(EvidenceDB.user_id == user_id)
            .all()
        )
        
    def get_by_source(
    self,
    source_type: EvidenceSourceType,
    source_id: str | None,
) -> EvidenceDB | None:
        return (
            self.session.query(EvidenceDB)
            .filter(
                EvidenceDB.source_type == source_type,
                EvidenceDB.source_id == source_id,
            )
            .first()
        )
        
    def create(
    self,
    *,
    evidence_id: str,
    user_id: str,
    source_type: EvidenceSourceType,
    title: str,
    description: str | None = None,
    source_id: str | None = None,
    source_url: str | None = None,
    captured_at: datetime,
    source_updated_at: datetime | None = None,
    content_hash: str | None = None,
    status: EvidenceStatus = EvidenceStatus.ACTIVE,
) -> EvidenceDB:
        now = datetime.now(UTC)

        evidence = EvidenceDB(
            id=evidence_id,
            user_id=user_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            description=description,
            source_url=source_url,
            captured_at=captured_at,
            source_updated_at=source_updated_at,
            content_hash=content_hash,
            status=status,
            created_at=now,
            updated_at=now,
        )

        self.session.add(evidence)
        self.session.flush()

        return evidence