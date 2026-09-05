from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.db.models.evidence_version import EvidenceVersionDB
from app.repositories.evidence_version import EvidenceVersionRepository
from app.services.evidence_version import EvidenceVersionService


def test_create_first_version():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceVersionRepository)
    repository.get_by_evidence_id.return_value = []
    repository.create.return_value = MagicMock(spec=EvidenceVersionDB)

    service = EvidenceVersionService(session)
    service.repository = repository

    captured_at = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)

    with patch(
        "app.services.evidence_version.uuid4",
        return_value="version-1",
    ):
        result = service.create_version(
            evidence_id="evidence-1",
            content="Version one",
            content_hash="hash-1",
            captured_at=captured_at,
        )

    assert isinstance(result, EvidenceVersionDB)
    repository.create.assert_called_once_with(
        version_id="version-1",
        evidence_id="evidence-1",
        version=1,
        content="Version one",
        content_hash="hash-1",
        captured_at=captured_at,
        source_updated_at=None,
    )
    session.commit.assert_called_once()


def test_create_next_version_uses_highest_existing_version():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceVersionRepository)

    version_1 = MagicMock(spec=EvidenceVersionDB)
    version_1.version = 1
    version_3 = MagicMock(spec=EvidenceVersionDB)
    version_3.version = 3

    repository.get_by_evidence_id.return_value = [version_1, version_3]
    repository.create.return_value = MagicMock(spec=EvidenceVersionDB)

    service = EvidenceVersionService(session)
    service.repository = repository

    captured_at = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)

    with patch(
        "app.services.evidence_version.uuid4",
        return_value="version-4",
    ):
        result = service.create_version(
            evidence_id="evidence-1",
            content="Version four",
            content_hash="hash-4",
            captured_at=captured_at,
        )

    assert isinstance(result, EvidenceVersionDB)
    repository.create.assert_called_once_with(
        version_id="version-4",
        evidence_id="evidence-1",
        version=4,
        content="Version four",
        content_hash="hash-4",
        captured_at=captured_at,
        source_updated_at=None,
    )
    session.commit.assert_called_once()


def test_get_version_by_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceVersionRepository)
    expected = MagicMock(spec=EvidenceVersionDB)
    repository.get_by_id.return_value = expected

    service = EvidenceVersionService(session)
    service.repository = repository

    assert service.get_version_by_id("version-1") is expected
    repository.get_by_id.assert_called_once_with("version-1")


def test_get_versions_by_evidence_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceVersionRepository)
    expected = [MagicMock(spec=EvidenceVersionDB)]
    repository.get_by_evidence_id.return_value = expected

    service = EvidenceVersionService(session)
    service.repository = repository

    assert service.get_versions_by_evidence_id("evidence-1") == expected
    repository.get_by_evidence_id.assert_called_once_with("evidence-1")


def test_get_version():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceVersionRepository)
    expected = MagicMock(spec=EvidenceVersionDB)
    repository.get_by_evidence_id_and_version.return_value = expected

    service = EvidenceVersionService(session)
    service.repository = repository

    assert service.get_version("evidence-1", 2) is expected
    repository.get_by_evidence_id_and_version.assert_called_once_with(
        "evidence-1",
        2,
    )
