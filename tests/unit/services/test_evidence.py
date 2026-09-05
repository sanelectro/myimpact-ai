from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceDB
from app.models.evidence import EvidenceCreate, EvidenceSourceType
from app.repositories.evidence import EvidenceRepository
from app.services.evidence import EvidenceService


def test_create_evidence():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceRepository)
    repository.create.return_value = MagicMock(spec=EvidenceDB)

    service = EvidenceService(session)
    service.repository = repository

    captured_at = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
    evidence_data = EvidenceCreate(
        user_id="user-1",
        source_type=EvidenceSourceType.GITHUB,
        source_id="PR-123",
        title="Implemented monitoring",
        description="Added monitoring.",
        source_url="https://example.com/pr/123",
        captured_at=captured_at,
        content_hash="hash-1",
    )

    with patch("app.services.evidence.uuid4", return_value="evidence-123"):
        result = service.create_evidence(evidence_data)

    assert isinstance(result, EvidenceDB)
    repository.create.assert_called_once_with(
        evidence_id="evidence-123",
        user_id="user-1",
        source_type=EvidenceSourceType.GITHUB,
        title="Implemented monitoring",
        description="Added monitoring.",
        source_id="PR-123",
        source_url="https://example.com/pr/123",
        captured_at=captured_at,
        source_updated_at=None,
        content_hash="hash-1",
    )
    session.commit.assert_called_once()


def test_get_evidence_by_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceRepository)
    expected = MagicMock(spec=EvidenceDB)
    repository.get_by_id.return_value = expected

    service = EvidenceService(session)
    service.repository = repository

    assert service.get_evidence_by_id("evidence-123") is expected
    repository.get_by_id.assert_called_once_with("evidence-123")


def test_get_evidence_by_user_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceRepository)
    expected = [MagicMock(spec=EvidenceDB)]
    repository.get_by_user_id.return_value = expected

    service = EvidenceService(session)
    service.repository = repository

    assert service.get_evidence_by_user_id("user-123") == expected
    repository.get_by_user_id.assert_called_once_with("user-123")


def test_get_evidence_by_source():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceRepository)
    expected = MagicMock(spec=EvidenceDB)
    repository.get_by_source.return_value = expected

    service = EvidenceService(session)
    service.repository = repository

    assert service.get_evidence_by_source(
        EvidenceSourceType.GITHUB,
        "PR-123",
    ) is expected
    repository.get_by_source.assert_called_once_with(
        EvidenceSourceType.GITHUB,
        "PR-123",
    )


def test_get_evidence_by_id_returns_none():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceRepository)
    repository.get_by_id.return_value = None

    service = EvidenceService(session)
    service.repository = repository

    assert service.get_evidence_by_id("missing-evidence") is None
