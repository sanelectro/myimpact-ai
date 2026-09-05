from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.evidence_version import EvidenceVersionDB
from app.repositories.evidence_version import EvidenceVersionRepository
from datetime import UTC, datetime

def test_get_by_id_returns_evidence_version():
    session = MagicMock(spec=Session)
    expected_version = MagicMock(spec=EvidenceVersionDB)

    session.get.return_value = expected_version

    repository = EvidenceVersionRepository(session)

    result = repository.get_by_id("version-123")

    assert result is expected_version
    session.get.assert_called_once_with(
        EvidenceVersionDB,
        "version-123",
    )


def test_get_by_id_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    session.get.return_value = None

    repository = EvidenceVersionRepository(session)

    result = repository.get_by_id("missing-version")

    assert result is None
    session.get.assert_called_once_with(
        EvidenceVersionDB,
        "missing-version",
    )
    
    
def test_get_by_evidence_id_returns_versions_in_order():
    session = MagicMock(spec=Session)

    version_1 = MagicMock(spec=EvidenceVersionDB)
    version_2 = MagicMock(spec=EvidenceVersionDB)
    version_3 = MagicMock(spec=EvidenceVersionDB)

    expected_versions = [version_1, version_2, version_3]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    ordered_query = filtered_query.order_by.return_value
    ordered_query.all.return_value = expected_versions

    repository = EvidenceVersionRepository(session)

    result = repository.get_by_evidence_id("evidence-123")

    assert result == expected_versions

    session.query.assert_called_once_with(EvidenceVersionDB)
    query.filter.assert_called_once()
    filtered_query.order_by.assert_called_once()
    ordered_query.all.assert_called_once()
    
def test_get_by_evidence_id_returns_empty_list_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    ordered_query = filtered_query.order_by.return_value
    ordered_query.all.return_value = []

    repository = EvidenceVersionRepository(session)

    result = repository.get_by_evidence_id("missing-evidence")

    assert result == []

    session.query.assert_called_once_with(EvidenceVersionDB)
    query.filter.assert_called_once()
    filtered_query.order_by.assert_called_once()
    ordered_query.all.assert_called_once()
    
    
def test_get_by_evidence_id_and_version_returns_version():
    session = MagicMock(spec=Session)
    expected_version = MagicMock(spec=EvidenceVersionDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = expected_version

    repository = EvidenceVersionRepository(session)

    result = repository.get_by_evidence_id_and_version(
        "evidence-123",
        2,
    )

    assert result is expected_version
    session.query.assert_called_once_with(EvidenceVersionDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()

    filter_arguments = query.filter.call_args.args

    assert len(filter_arguments) == 2
    assert filter_arguments[0].right.value == "evidence-123"
    assert filter_arguments[1].right.value == 2


def test_get_by_evidence_id_and_version_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = None

    repository = EvidenceVersionRepository(session)

    result = repository.get_by_evidence_id_and_version(
        "missing-evidence",
        99,
    )

    assert result is None
    session.query.assert_called_once_with(EvidenceVersionDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()
    

def test_create_evidence_version():
    session = MagicMock(spec=Session)
    repository = EvidenceVersionRepository(session)

    captured_at = datetime(2026, 9, 5, 10, 30, tzinfo=UTC)
    source_updated_at = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)

    result = repository.create(
        version_id="version-123",
        evidence_id="evidence-123",
        version=2,
        content="Implemented deployment monitoring with CPU and memory alerts.",
        content_hash="abc123",
        captured_at=captured_at,
        source_updated_at=source_updated_at,
    )

    assert isinstance(result, EvidenceVersionDB)
    assert result.id == "version-123"
    assert result.evidence_id == "evidence-123"
    assert result.version == 2
    assert result.content == (
        "Implemented deployment monitoring with CPU and memory alerts."
    )
    assert result.content_hash == "abc123"
    assert result.captured_at == captured_at
    assert result.source_updated_at == source_updated_at
    assert result.created_at is not None

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()
    
    
def test_create_evidence_version_without_source_updated_at():
    session = MagicMock(spec=Session)
    repository = EvidenceVersionRepository(session)

    captured_at = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)

    result = repository.create(
        version_id="version-456",
        evidence_id="evidence-123",
        version=1,
        content="Implemented deployment monitoring.",
        content_hash="def456",
        captured_at=captured_at,
    )

    assert isinstance(result, EvidenceVersionDB)
    assert result.id == "version-456"
    assert result.evidence_id == "evidence-123"
    assert result.version == 1
    assert result.content == "Implemented deployment monitoring."
    assert result.content_hash == "def456"
    assert result.captured_at == captured_at
    assert result.source_updated_at is None
    assert result.created_at is not None

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()