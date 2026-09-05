from datetime import UTC, datetime
from sqlalchemy.exc import IntegrityError
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceSourceType
from app.repositories.evidence import EvidenceRepository
from app.repositories.evidence_version import EvidenceVersionRepository


@pytest.mark.integration
def test_create_and_get_evidence_versions():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    evidence_id = f"test-evidence-{uuid4()}"
    version_1_id = f"test-version-{uuid4()}"
    version_2_id = f"test-version-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Evidence Version Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        evidence_repository = EvidenceRepository(session)

        evidence_repository.create(
            evidence_id=evidence_id,
            user_id=user_id,
            source_type=EvidenceSourceType.GITHUB,
            source_id=f"PR-{uuid4()}",
            title="Implemented deployment monitoring",
            captured_at=datetime.now(UTC),
        )

        session.commit()

        repository = EvidenceVersionRepository(session)

        captured_at = datetime.now(UTC)

        repository.create(
            version_id=version_1_id,
            evidence_id=evidence_id,
            version=1,
            content="Implemented deployment monitoring.",
            content_hash="hash-v1",
            captured_at=captured_at,
        )

        repository.create(
            version_id=version_2_id,
            evidence_id=evidence_id,
            version=2,
            content="Implemented deployment monitoring with CPU and memory alerts.",
            content_hash="hash-v2",
            captured_at=captured_at,
        )

        session.commit()

        result_by_id = repository.get_by_id(version_1_id)

        assert result_by_id is not None
        assert result_by_id.evidence_id == evidence_id
        assert result_by_id.version == 1
        assert result_by_id.content == "Implemented deployment monitoring."

        versions = repository.get_by_evidence_id(evidence_id)

        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[1].version == 2

        result_by_version = repository.get_by_evidence_id_and_version(
            evidence_id,
            2,
        )

        assert result_by_version is not None
        assert result_by_version.id == version_2_id
        assert result_by_version.version == 2
        assert result_by_version.content_hash == "hash-v2"

    finally:
        session.execute(
            delete(EvidenceVersionDB).where(
                EvidenceVersionDB.evidence_id == evidence_id
            )
        )
        session.execute(
            delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()
        
        
@pytest.mark.integration
def test_create_duplicate_evidence_version_fails():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    evidence_id = f"test-evidence-{uuid4()}"
    version_1_id = f"test-version-{uuid4()}"
    version_2_id = f"test-version-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Duplicate Version Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        evidence_repository = EvidenceRepository(session)

        evidence_repository.create(
            evidence_id=evidence_id,
            user_id=user_id,
            source_type=EvidenceSourceType.GITHUB,
            title="Test evidence",
            captured_at=datetime.now(UTC),
        )

        session.commit()

        repository = EvidenceVersionRepository(session)

        repository.create(
            version_id=version_1_id,
            evidence_id=evidence_id,
            version=1,
            content="First version",
            content_hash="hash-v1",
            captured_at=datetime.now(UTC),
        )

        session.commit()

        with pytest.raises(IntegrityError):
            repository.create(
                version_id=version_2_id,
                evidence_id=evidence_id,
                version=1,
                content="Duplicate first version",
                content_hash="hash-duplicate",
                captured_at=datetime.now(UTC),
            )

        session.rollback()

    finally:
        session.execute(
            delete(EvidenceVersionDB).where(
                EvidenceVersionDB.evidence_id == evidence_id
            )
        )
        session.execute(
            delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()