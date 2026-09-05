from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.evidence_mapping import EvidenceMappingDB
from app.repositories.evidence_mapping import EvidenceMappingRepository
from datetime import UTC, datetime

from app.models.evidence_mapping import EvidenceRelevance


def test_get_by_id_returns_mapping():
    session = MagicMock(spec=Session)
    expected_mapping = MagicMock(spec=EvidenceMappingDB)

    session.get.return_value = expected_mapping

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_id("mapping-123")

    assert result is expected_mapping
    session.get.assert_called_once_with(
        EvidenceMappingDB,
        "mapping-123",
    )


def test_get_by_id_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    session.get.return_value = None

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_id("missing-mapping")

    assert result is None
    session.get.assert_called_once_with(
        EvidenceMappingDB,
        "missing-mapping",
    )
    
    
def test_get_by_evidence_id_returns_mappings():
    session = MagicMock(spec=Session)

    mapping_1 = MagicMock(spec=EvidenceMappingDB)
    mapping_2 = MagicMock(spec=EvidenceMappingDB)

    expected_mappings = [mapping_1, mapping_2]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = expected_mappings

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_evidence_id("evidence-123")

    assert result == expected_mappings
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
    
    
def test_get_by_evidence_id_returns_mappings():
    session = MagicMock(spec=Session)

    mapping_1 = MagicMock(spec=EvidenceMappingDB)
    mapping_2 = MagicMock(spec=EvidenceMappingDB)

    expected_mappings = [mapping_1, mapping_2]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = expected_mappings

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_evidence_id("evidence-123")

    assert result == expected_mappings
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
    
def test_get_by_evidence_id_returns_empty_list_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = []

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_evidence_id("missing-evidence")

    assert result == []
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
    
def test_get_by_goal_id_returns_mappings():
    session = MagicMock(spec=Session)

    mapping_1 = MagicMock(spec=EvidenceMappingDB)
    mapping_2 = MagicMock(spec=EvidenceMappingDB)

    expected_mappings = [mapping_1, mapping_2]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = expected_mappings

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_goal_id("goal-123")

    assert result == expected_mappings
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()


def test_get_by_goal_id_returns_empty_list_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = []

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_goal_id("missing-goal")

    assert result == []
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()
    
def test_get_by_evidence_and_goal_returns_mapping():
    session = MagicMock(spec=Session)
    expected_mapping = MagicMock(spec=EvidenceMappingDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = expected_mapping

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_evidence_and_goal(
        "evidence-123",
        "goal-123",
    )

    assert result is expected_mapping
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()

    filter_arguments = query.filter.call_args.args

    assert len(filter_arguments) == 2
    assert filter_arguments[0].right.value == "evidence-123"
    assert filter_arguments[1].right.value == "goal-123"
    
def test_get_by_evidence_and_goal_returns_mapping():
    session = MagicMock(spec=Session)
    expected_mapping = MagicMock(spec=EvidenceMappingDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = expected_mapping

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_evidence_and_goal(
        "evidence-123",
        "goal-123",
    )

    assert result is expected_mapping
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()

    filter_arguments = query.filter.call_args.args

    assert len(filter_arguments) == 2
    assert filter_arguments[0].right.value == "evidence-123"
    assert filter_arguments[1].right.value == "goal-123"
    
def test_get_by_evidence_and_goal_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = None

    repository = EvidenceMappingRepository(session)

    result = repository.get_by_evidence_and_goal(
        "missing-evidence",
        "missing-goal",
    )

    assert result is None
    session.query.assert_called_once_with(EvidenceMappingDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()
    
    
def test_create_evidence_mapping():
    session = MagicMock(spec=Session)
    repository = EvidenceMappingRepository(session)

    result = repository.create(
        mapping_id="mapping-123",
        evidence_id="evidence-123",
        goal_id="goal-123",
        relevance=EvidenceRelevance.HIGH,
        confidence=0.95,
        reason="Evidence directly demonstrates progress toward the goal.",
    )

    assert isinstance(result, EvidenceMappingDB)
    assert result.id == "mapping-123"
    assert result.evidence_id == "evidence-123"
    assert result.goal_id == "goal-123"
    assert result.relevance == EvidenceRelevance.HIGH
    assert result.confidence == 0.95
    assert result.reason == (
        "Evidence directly demonstrates progress toward the goal."
    )
    assert result.created_at is not None
    assert result.updated_at is not None

    assert result.created_at.tzinfo == UTC
    assert result.updated_at.tzinfo == UTC

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()
    
def test_create_evidence_mapping_without_reason():
    session = MagicMock(spec=Session)
    repository = EvidenceMappingRepository(session)

    result = repository.create(
        mapping_id="mapping-456",
        evidence_id="evidence-123",
        goal_id="goal-456",
        relevance=EvidenceRelevance.MEDIUM,
        confidence=0.75,
    )

    assert isinstance(result, EvidenceMappingDB)
    assert result.id == "mapping-456"
    assert result.evidence_id == "evidence-123"
    assert result.goal_id == "goal-456"
    assert result.relevance == EvidenceRelevance.MEDIUM
    assert result.confidence == 0.75
    assert result.reason is None
    assert result.created_at is not None
    assert result.updated_at is not None

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()