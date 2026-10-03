from unittest.mock import AsyncMock

import pytest

from app.exceptions import DocumentExpectationExtractionError
from app.models.expectation import ExpectationCategory
from app.models.llm import LLMResponse
from app.services.document_expectation import (
    DocumentExpectationExtractionService,
)
from app.services.llm.interface import ILLMService


@pytest.fixture
def llm_service() -> AsyncMock:
    return AsyncMock(spec=ILLMService)


@pytest.fixture
def service(
    llm_service: AsyncMock,
) -> DocumentExpectationExtractionService:
    return DocumentExpectationExtractionService(llm_service=llm_service)


async def test_extracts_structured_expectations(
    service: DocumentExpectationExtractionService,
    llm_service: AsyncMock,
):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"expectations":[{"category":"architecture",'
            '"description":"Lead architecture initiatives",'
            '"evidence_hints":["Architecture decisions","Design documents"],'
            '"source_reference":{"section":"Technical Leadership",'
            '"text_span":"Lead architecture initiatives"},'
            '"confidence":0.94}]}'
        ),
        model="test-model",
    )

    result = await service.extract(
        "## Technical Leadership\nLead architecture initiatives."
    )

    assert len(result.expectations) == 1
    expectation = result.expectations[0]
    assert expectation.category == ExpectationCategory.ARCHITECTURE
    assert expectation.description == "Lead architecture initiatives"
    assert expectation.evidence_hints == [
        "Architecture decisions",
        "Design documents",
    ]
    assert expectation.source_reference is not None
    assert expectation.source_reference.section == "Technical Leadership"
    assert expectation.confidence == 0.94

    request = llm_service.generate.await_args.args[0]
    assert "Do not claim that an expectation was achieved" in request.prompt
    assert "business_domain_impact" in request.prompt


async def test_returns_empty_result_when_no_expectations(
    service: DocumentExpectationExtractionService,
    llm_service: AsyncMock,
):
    llm_service.generate.return_value = LLMResponse(
        content='{"expectations":[]}'
    )

    result = await service.extract("General company announcement")

    assert result.expectations == []


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"expectations":[{"category":"unsupported",'
        '"description":"x","confidence":0.9}]}',
        '{"expectations":[{"category":"architecture",'
        '"description":"x","confidence":1.5}]}',
        '{"expectations":[{"category":"architecture",'
        '"description":"","confidence":0.9}]}',
    ],
)
async def test_rejects_invalid_llm_response(
    service: DocumentExpectationExtractionService,
    llm_service: AsyncMock,
    content: str,
):
    llm_service.generate.return_value = LLMResponse(content=content)

    with pytest.raises(
        DocumentExpectationExtractionError,
        match="invalid response",
    ):
        await service.extract("Lead architecture initiatives")


async def test_wraps_provider_failure(
    service: DocumentExpectationExtractionService,
    llm_service: AsyncMock,
):
    llm_service.generate.side_effect = RuntimeError("provider secret")

    with pytest.raises(
        DocumentExpectationExtractionError,
        match="provider failed",
    ) as error:
        await service.extract("Lead architecture initiatives")

    assert "provider secret" not in str(error.value)


async def test_rejects_empty_content(
    service: DocumentExpectationExtractionService,
    llm_service: AsyncMock,
):
    with pytest.raises(
        DocumentExpectationExtractionError,
        match="content is required",
    ):
        await service.extract("  ")

    llm_service.generate.assert_not_awaited()
