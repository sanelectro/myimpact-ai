from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceCreate, EvidenceSourceType
from app.models.user import UserCreate
from app.services.evidence import EvidenceService
from app.services.user import UserService


@pytest.mark.integration
def test_create_and_get_evidence():
    session = SessionLocal()
    user_id = None
    evidence_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Evidence Service User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        captured_at = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
        service = EvidenceService(session)

        evidence = service.create_evidence(
            EvidenceCreate(
                user_id=user_id,
                source_type=EvidenceSourceType.GITHUB,
                source_id="PR-123",
                title="Implemented monitoring",
                description="Added monitoring.",
                source_url="https://example.com/pr/123",
                captured_at=captured_at,
                content_hash="hash-1",
            )
        )
        evidence_id = evidence.id

        result = service.get_evidence_by_id(evidence_id)

        assert result is not None
        assert result.id == evidence_id
        assert result.user_id == user_id
        assert result.source_type == EvidenceSourceType.GITHUB
        assert result.source_id == "PR-123"

        by_source = service.get_evidence_by_source(
            EvidenceSourceType.GITHUB,
            "PR-123",
        )
        assert by_source is not None
        assert by_source.id == evidence_id

    finally:
        if evidence_id is not None:
            session.execute(
                delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
            )
        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
        session.commit()
        session.close()
