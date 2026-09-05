from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceSourceType
from app.repositories.evidence import EvidenceRepository


@pytest.mark.integration
def test_create_and_get_evidence():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    evidence_id = f"test-evidence-{uuid4()}"
    source_id = f"PR-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Evidence Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        repository = EvidenceRepository(session)

        captured_at = datetime.now(UTC)

        repository.create(
            evidence_id=evidence_id,
            user_id=user_id,
            source_type=EvidenceSourceType.GITHUB,
            source_id=source_id,
            title="Implemented deployment monitoring",
            description="Added deployment monitoring alerts.",
            captured_at=captured_at,
        )

        session.commit()

        result_by_id = repository.get_by_id(evidence_id)
        result_by_user = repository.get_by_user_id(user_id)
        result_by_source = repository.get_by_source(
            EvidenceSourceType.GITHUB,
            source_id,
        )

        assert result_by_id is not None
        assert result_by_id.id == evidence_id
        assert result_by_id.user_id == user_id
        assert result_by_id.title == "Implemented deployment monitoring"

        assert len(result_by_user) == 1
        assert result_by_user[0].id == evidence_id

        assert result_by_source is not None
        assert result_by_source.id == evidence_id

    finally:
        session.execute(
            delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()