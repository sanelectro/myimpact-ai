from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.exceptions import EvidencePersistenceError
from app.models.document_expectation import DocumentExpectation
from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.models.evidence import EvidenceSourceType
from app.models.evidence_mapping import EvidenceRelevance
from app.models.expectation import ExpectationCategory
from app.models.impact_intelligence import (
    EvidenceCandidate,
    EvidenceEvaluation,
    EvidenceSupportLevel,
)
from app.services.knowledge.evidence_persistence import EvidencePersistenceService


def make_expectation() -> DocumentExpectation:
    now = datetime.now(UTC)
    return DocumentExpectation(
        id="expectation-1",
        document_id="document-1",
        category=ExpectationCategory.ARCHITECTURE,
        description="Drive architecture decisions across the platform",
        evidence_hints=["architecture reviews"],
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )


def make_candidate(expectation_id: str = "expectation-1") -> EvidenceCandidate:
    return EvidenceCandidate(
        expectation_id=expectation_id,
        search_result=KnowledgeSearchResult(
            chunk_id="chunk-1",
            document_id="document-1",
            content="Led architecture decisions for the platform.",
            heading_path=["Architecture"],
            document_type="role",
            scope_type="employee",
            scope_id="user-1",
            metadata={},
            similarity=0.91,
        ),
    )


def make_evaluation(
    level: EvidenceSupportLevel = EvidenceSupportLevel.STRONG,
    *,
    supports: bool = True,
) -> EvidenceEvaluation:
    return EvidenceEvaluation(
        candidate_chunk_id="chunk-1",
        supports_expectation=supports,
        support_level=level,
        confidence=0.93,
        rationale="The evidence explicitly describes architecture decisions.",
    )


def make_service() -> EvidencePersistenceService:
    service = EvidencePersistenceService(MagicMock())
    service.evidence_repository = MagicMock()
    service.version_repository = MagicMock()
    service.mapping_repository = MagicMock()
    service.goal_repository = MagicMock()
    service.commit = MagicMock()
    service.rollback = MagicMock()
    return service


def make_goal(user_id: str = "user-1"):
    return MagicMock(id="goal-1", user_id=user_id)


def make_evidence() -> EvidenceDB:
    return EvidenceDB(
        id="evidence-1",
        user_id="user-1",
        source_type=EvidenceSourceType.DOCUMENT,
        source_id="chunk-1",
        title="Drive architecture decisions across the platform",
        description="Led architecture decisions for the platform.",
        captured_at=datetime.now(UTC),
        content_hash="hash",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def make_version() -> EvidenceVersionDB:
    return EvidenceVersionDB(
        id="version-1",
        evidence_id="evidence-1",
        version=1,
        content="Led architecture decisions for the platform.",
        content_hash="hash",
        captured_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def make_mapping() -> EvidenceMappingDB:
    return EvidenceMappingDB(
        id="mapping-1",
        evidence_id="evidence-1",
        goal_id="goal-1",
        relevance=EvidenceRelevance.HIGH,
        confidence=0.93,
        reason="The evidence explicitly describes architecture decisions.",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_persists_supported_evidence_and_mapping():
    service = make_service()
    service.goal_repository.get_by_id.return_value = make_goal()
    service.evidence_repository.get_by_source_for_user.return_value = None
    service.version_repository.get_by_evidence_id.return_value = []
    service.mapping_repository.get_by_evidence_and_goal.return_value = None
    evidence = make_evidence()
    version = make_version()
    mapping = make_mapping()
    service.evidence_repository.create.return_value = evidence
    service.version_repository.create.return_value = version
    service.mapping_repository.create.return_value = mapping

    result = service.persist_evaluation(
        make_expectation(),
        make_candidate(),
        make_evaluation(),
        user_id="user-1",
        goal_id="goal-1",
    )

    assert result == (evidence, version, mapping)
    service.evidence_repository.create.assert_called_once()
    assert service.evidence_repository.create.call_args.kwargs["source_type"] == EvidenceSourceType.DOCUMENT
    assert service.evidence_repository.create.call_args.kwargs["source_id"] == "chunk-1"
    service.version_repository.create.assert_called_once()
    assert service.version_repository.create.call_args.kwargs["version"] == 1
    service.mapping_repository.create.assert_called_once()
    assert service.mapping_repository.create.call_args.kwargs["relevance"] == EvidenceRelevance.HIGH
    service.commit.assert_called_once()


def test_moderate_support_maps_to_medium_relevance():
    service = make_service()
    service.goal_repository.get_by_id.return_value = make_goal()
    service.evidence_repository.get_by_source_for_user.return_value = make_evidence()
    service.version_repository.get_by_evidence_id.return_value = [make_version()]
    service.mapping_repository.get_by_evidence_and_goal.return_value = None
    mapping = make_mapping()
    mapping.relevance = EvidenceRelevance.MEDIUM
    service.mapping_repository.create.return_value = mapping

    service.persist_evaluation(
        make_expectation(),
        make_candidate(),
        make_evaluation(EvidenceSupportLevel.MODERATE),
        user_id="user-1",
        goal_id="goal-1",
    )

    assert service.mapping_repository.create.call_args.kwargs["relevance"] == EvidenceRelevance.MEDIUM
    service.evidence_repository.create.assert_not_called()
    service.version_repository.create.assert_not_called()


@pytest.mark.parametrize(
    "level,supports",
    [
        (EvidenceSupportLevel.NONE, False),
        (EvidenceSupportLevel.WEAK, True),
        (EvidenceSupportLevel.STRONG, False),
    ],
)
def test_does_not_persist_unsupported_evidence(level, supports):
    service = make_service()

    result = service.persist_evaluation(
        make_expectation(),
        make_candidate(),
        make_evaluation(level, supports=supports),
        user_id="user-1",
        goal_id="goal-1",
    )

    assert result is None
    service.goal_repository.get_by_id.assert_not_called()
    service.commit.assert_not_called()


def test_reuses_existing_evidence_and_mapping_idempotently():
    service = make_service()
    service.goal_repository.get_by_id.return_value = make_goal()
    evidence = make_evidence()
    version = make_version()
    mapping = make_mapping()
    service.evidence_repository.get_by_source_for_user.return_value = evidence
    service.version_repository.get_by_evidence_id.return_value = [version]
    service.mapping_repository.get_by_evidence_and_goal.return_value = mapping

    result = service.persist_evaluation(
        make_expectation(),
        make_candidate(),
        make_evaluation(),
        user_id="user-1",
        goal_id="goal-1",
    )

    assert result == (evidence, version, mapping)
    service.evidence_repository.create.assert_not_called()
    service.version_repository.create.assert_not_called()
    service.mapping_repository.create.assert_not_called()
    service.commit.assert_called_once()


def test_rejects_goal_from_another_user():
    service = make_service()
    service.goal_repository.get_by_id.return_value = make_goal("other-user")

    with pytest.raises(EvidencePersistenceError, match="does not belong"):
        service.persist_evaluation(
            make_expectation(),
            make_candidate(),
            make_evaluation(),
            user_id="user-1",
            goal_id="goal-1",
        )


def test_rejects_candidate_for_different_expectation():
    service = make_service()

    with pytest.raises(EvidencePersistenceError, match="does not belong"):
        service.persist_evaluation(
            make_expectation(),
            make_candidate("other-expectation"),
            make_evaluation(),
            user_id="user-1",
            goal_id="goal-1",
        )
