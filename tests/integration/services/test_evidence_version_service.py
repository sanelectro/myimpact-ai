from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceCreate, EvidenceSourceType
from app.models.user import UserCreate
from app.services.evidence import EvidenceService
from app.services.evidence_version import EvidenceVersionService
from app.services.user import UserService


@pytest.mark.integration
def test_create_multiple_evidence_versions():
    session = SessionLocal()
    user_id = None
    evidence_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Evidence Version Service User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        evidence = EvidenceService(session).create_evidence(
            EvidenceCreate(
                user_id=user_id,
                source_type=EvidenceSourceType.GITHUB,
                source_id=f"PR-{uuid4()}",
                title="Deployment monitoring",
                captured_at=datetime.now(UTC),
            )
        )
        evidence_id = evidence.id

        service = EvidenceVersionService(session)

        version_1 = service.create_version(
            evidence_id=evidence_id,
            content="Initial monitoring implementation.",
            content_hash="hash-v1",
            captured_at=datetime.now(UTC),
        )

        version_2 = service.create_version(
            evidence_id=evidence_id,
            content="Monitoring implementation with alerts.",
            content_hash="hash-v2",
            captured_at=datetime.now(UTC),
        )

        assert version_1.version == 1
        assert version_2.version == 2

        versions = service.get_versions_by_evidence_id(evidence_id)

        assert [version.version for version in versions] == [1, 2]

        latest = service.get_version(evidence_id, 2)

        assert latest is not None
        assert latest.content_hash == "hash-v2"

    finally:
        if evidence_id is not None:
            session.execute(
                delete(EvidenceVersionDB).where(
                    EvidenceVersionDB.evidence_id == evidence_id
                )
            )
            session.execute(
                delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
            )
        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
        session.commit()
        session.close()
