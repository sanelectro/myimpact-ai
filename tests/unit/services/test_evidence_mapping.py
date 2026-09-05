from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.db.models.evidence_mapping import EvidenceMappingDB
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.models.evidence_mapping import EvidenceRelevance
from app.repositories.evidence_mapping import EvidenceMappingRepository
from app.services.evidence_mapping import EvidenceMappingService


def test_create_mapping():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceMappingRepository)
    repository.get_by_evidence_and_goal.return_value = None
    repository.create.return_value = MagicMock(spec=EvidenceMappingDB)

    service = EvidenceMappingService(session)
    service.repository = repository

    with patch(
        "app.services.evidence_mapping.uuid4",
        return_value="mapping-123",
    ):
        result = service.create_mapping(
            evidence_id="evidence-123",
            goal_id="goal-123",
            relevance=EvidenceRelevance.HIGH,
            confidence=0.95,
            reason="Directly supports the goal.",
        )

    assert isinstance(result, EvidenceMappingDB)
    repository.create.assert_called_once_with(
        mapping_id="mapping-123",
        evidence_id="evidence-123",
        goal_id="goal-123",
        relevance=EvidenceRelevance.HIGH,
        confidence=0.95,
        reason="Directly supports the goal.",
    )
    session.commit.assert_called_once()


def test_create_mapping_rejects_existing_mapping():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceMappingRepository)
    repository.get_by_evidence_and_goal.return_value = MagicMock(
        spec=EvidenceMappingDB
    )

    service = EvidenceMappingService(session)
    service.repository = repository

    with pytest.raises(
        EvidenceMappingAlreadyExistsError,
        match="already mapped",
    ):
        service.create_mapping(
            evidence_id="evidence-123",
            goal_id="goal-123",
            relevance=EvidenceRelevance.HIGH,
            confidence=0.95,
        )

    repository.create.assert_not_called()
    session.commit.assert_not_called()


def test_get_mapping_by_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceMappingRepository)
    expected = MagicMock(spec=EvidenceMappingDB)
    repository.get_by_id.return_value = expected

    service = EvidenceMappingService(session)
    service.repository = repository

    assert service.get_mapping_by_id("mapping-123") is expected
    repository.get_by_id.assert_called_once_with("mapping-123")


def test_get_mappings_by_evidence_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceMappingRepository)
    expected = [MagicMock(spec=EvidenceMappingDB)]
    repository.get_by_evidence_id.return_value = expected

    service = EvidenceMappingService(session)
    service.repository = repository

    assert service.get_mappings_by_evidence_id("evidence-123") == expected
    repository.get_by_evidence_id.assert_called_once_with("evidence-123")


def test_get_mappings_by_goal_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceMappingRepository)
    expected = [MagicMock(spec=EvidenceMappingDB)]
    repository.get_by_goal_id.return_value = expected

    service = EvidenceMappingService(session)
    service.repository = repository

    assert service.get_mappings_by_goal_id("goal-123") == expected
    repository.get_by_goal_id.assert_called_once_with("goal-123")


def test_get_mapping_by_evidence_and_goal():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=EvidenceMappingRepository)
    expected = MagicMock(spec=EvidenceMappingDB)
    repository.get_by_evidence_and_goal.return_value = expected

    service = EvidenceMappingService(session)
    service.repository = repository

    assert service.get_mapping_by_evidence_and_goal(
        "evidence-123",
        "goal-123",
    ) is expected
    repository.get_by_evidence_and_goal.assert_called_once_with(
        "evidence-123",
        "goal-123",
    )
