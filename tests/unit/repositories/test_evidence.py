from datetime import UTC, datetime
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.evidence import EvidenceDB
from app.models.evidence import EvidenceSourceType, EvidenceStatus
from app.repositories.evidence import EvidenceRepository


def test_get_by_id_returns_evidence():
    session = MagicMock(spec=Session)
    expected_evidence = MagicMock(spec=EvidenceDB)

    session.get.return_value = expected_evidence

    repository = EvidenceRepository(session)

    result = repository.get_by_id("evidence-123")

    assert result is expected_evidence
    session.get.assert_called_once_with(EvidenceDB, "evidence-123")


def test_get_by_id_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    session.get.return_value = None

    repository = EvidenceRepository(session)

    result = repository.get_by_id("missing-evidence")

    assert result is None
    session.get.assert_called_once_with(EvidenceDB, "missing-evidence")
    
    
def test_get_by_user_id_returns_evidence():
    session = MagicMock(spec=Session)
    expected_evidence = [
        MagicMock(spec=EvidenceDB),
        MagicMock(spec=EvidenceDB),
    ]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = expected_evidence

    repository = EvidenceRepository(session)

    result = repository.get_by_user_id("user-123")

    assert result == expected_evidence
    session.query.assert_called_once_with(EvidenceDB)
    query.filter.assert_called_once()

    filter_argument = query.filter.call_args.args[0]

    assert str(filter_argument) == "evidence.user_id = :user_id_1"
    assert filter_argument.right.value == "user-123"
    filtered_query.all.assert_called_once()


def test_get_by_user_id_returns_empty_list_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = []

    repository = EvidenceRepository(session)

    result = repository.get_by_user_id("user-123")

    assert result == []
    session.query.assert_called_once_with(EvidenceDB)
    query.filter.assert_called_once()

    filter_argument = query.filter.call_args.args[0]

    assert str(filter_argument) == "evidence.user_id = :user_id_1"
    assert filter_argument.right.value == "user-123"
    filtered_query.all.assert_called_once()
    
def test_get_by_source_returns_evidence():
    session = MagicMock(spec=Session)
    expected_evidence = MagicMock(spec=EvidenceDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = expected_evidence

    repository = EvidenceRepository(session)

    result = repository.get_by_source(
        EvidenceSourceType.GITHUB,
        "PR-1234",
    )

    assert result is expected_evidence
    session.query.assert_called_once_with(EvidenceDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()

    filter_arguments = query.filter.call_args.args

    assert len(filter_arguments) == 2
    assert filter_arguments[0].right.value == EvidenceSourceType.GITHUB.value
    assert filter_arguments[1].right.value == "PR-1234"
    
    
def test_get_by_source_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = None

    repository = EvidenceRepository(session)

    result = repository.get_by_source(
        EvidenceSourceType.GITHUB,
        "missing-pr",
    )

    assert result is None
    session.query.assert_called_once_with(EvidenceDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()
    
    
def test_create_evidence():
    session = MagicMock(spec=Session)
    repository = EvidenceRepository(session)

    captured_at = datetime(2026, 9, 5, 10, 30, tzinfo=UTC)
    source_updated_at = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)

    result = repository.create(
        evidence_id="evidence-123",
        user_id="user-123",
        source_type=EvidenceSourceType.GITHUB,
        source_id="PR-1234",
        title="Implemented deployment monitoring",
        description="Added CPU and memory monitoring.",
        source_url="https://github.com/example/repo/pull/1234",
        captured_at=captured_at,
        source_updated_at=source_updated_at,
        content_hash="abc123",
        status=EvidenceStatus.ACTIVE,
    )

    assert isinstance(result, EvidenceDB)
    assert result.id == "evidence-123"
    assert result.user_id == "user-123"
    assert result.source_type == EvidenceSourceType.GITHUB
    assert result.source_id == "PR-1234"
    assert result.title == "Implemented deployment monitoring"
    assert result.description == "Added CPU and memory monitoring."
    assert result.source_url == "https://github.com/example/repo/pull/1234"
    assert result.captured_at == captured_at
    assert result.source_updated_at == source_updated_at
    assert result.content_hash == "abc123"
    assert result.status == EvidenceStatus.ACTIVE
    assert result.created_at is not None
    assert result.updated_at is not None

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()
    
    
def test_create_evidence_with_optional_fields():
    session = MagicMock(spec=Session)
    repository = EvidenceRepository(session)

    captured_at = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)

    result = repository.create(
        evidence_id="evidence-456",
        user_id="user-123",
        source_type=EvidenceSourceType.JIRA,
        title="Completed performance improvement",
        captured_at=captured_at,
    )

    assert isinstance(result, EvidenceDB)
    assert result.id == "evidence-456"
    assert result.user_id == "user-123"
    assert result.source_type == EvidenceSourceType.JIRA
    assert result.title == "Completed performance improvement"

    assert result.description is None
    assert result.source_id is None
    assert result.source_url is None
    assert result.source_updated_at is None
    assert result.content_hash is None
    assert result.status == EvidenceStatus.ACTIVE

    assert result.created_at is not None
    assert result.updated_at is not None

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()