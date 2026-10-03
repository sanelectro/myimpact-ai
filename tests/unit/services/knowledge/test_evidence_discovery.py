from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.document_expectation import DocumentExpectation
from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.models.expectation import ExpectationCategory
from app.services.knowledge.evidence_discovery import EvidenceDiscoveryService


def make_expectation() -> DocumentExpectation:
    now = datetime.now(UTC)
    return DocumentExpectation(
        id="expectation-1",
        document_id="document-1",
        category=ExpectationCategory.ARCHITECTURE,
        description="Drive architecture decisions across the platform",
        evidence_hints=["architecture reviews", "technical decisions"],
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )


def make_result() -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        chunk_id="chunk-1",
        document_id="document-1",
        content="Led architecture decisions for the platform.",
        heading_path=["Architecture"],
        document_type="role",
        scope_type="employee",
        scope_id="user-1",
        metadata={},
        similarity=0.91,
    )


def test_build_query_uses_description_and_non_empty_hints():
    service = EvidenceDiscoveryService(MagicMock())

    assert service.build_query(make_expectation()) == (
        "Drive architecture decisions across the platform "
        "architecture reviews technical decisions"
    )


@pytest.mark.asyncio
async def test_discover_retrieves_with_expectation_document_scope():
    retrieval_service = MagicMock()
    retrieval_service.retrieve = AsyncMock(return_value=[make_result()])
    service = EvidenceDiscoveryService(retrieval_service)
    expectation = make_expectation()

    candidates = await service.discover(expectation, limit=3, user_id="user-1")

    retrieval_service.retrieve.assert_awaited_once_with(
        "Drive architecture decisions across the platform architecture reviews technical decisions",
        limit=3,
        document_id="document-1",
        user_id="user-1",
    )
    assert len(candidates) == 1
    assert candidates[0].expectation_id == "expectation-1"
    assert candidates[0].search_result == make_result()


@pytest.mark.asyncio
async def test_discover_returns_empty_when_retrieval_finds_nothing():
    retrieval_service = MagicMock()
    retrieval_service.retrieve = AsyncMock(return_value=[])
    service = EvidenceDiscoveryService(retrieval_service)

    assert await service.discover(make_expectation()) == []
