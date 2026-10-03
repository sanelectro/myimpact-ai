from unittest.mock import AsyncMock

import pytest

from app.exceptions import DocumentClassificationError
from app.models.document import DocumentType
from app.models.llm import LLMResponse
from app.services.document_classification import DocumentClassificationService
from app.services.llm.interface import ILLMService


@pytest.fixture
def llm_service() -> AsyncMock:
    return AsyncMock(spec=ILLMService)


@pytest.fixture
def service(llm_service: AsyncMock) -> DocumentClassificationService:
    return DocumentClassificationService(
        llm_service=llm_service,
        minimum_confidence=0.8,
    )


async def test_classifies_known_document_type(
    service: DocumentClassificationService,
    llm_service: AsyncMock,
):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"document_type":"goal","confidence":0.94,'
            '"reason":"Contains annual objectives."}'
        ),
        model="test-model",
    )

    result = await service.classify("# Annual Goals\nImprove reliability.")

    assert result.document_type == DocumentType.GOAL
    assert result.confidence == 0.94
    assert result.reason == "Contains annual objectives."
    request = llm_service.generate.await_args.args[0]
    assert "# Annual Goals" in request.prompt
    assert "unknown" in request.prompt


async def test_preserves_unknown_document_type(
    service: DocumentClassificationService,
    llm_service: AsyncMock,
):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"document_type":"unknown","confidence":0.9,'
            '"reason":"No supported category applies."}'
        )
    )

    result = await service.classify("Unrelated content")

    assert result.document_type == DocumentType.UNKNOWN


async def test_low_confidence_is_treated_as_unknown(
    service: DocumentClassificationService,
    llm_service: AsyncMock,
):
    llm_service.generate.return_value = LLMResponse(
        content=(
            '{"document_type":"goal","confidence":0.79,'
            '"reason":"May contain an objective."}'
        )
    )

    result = await service.classify("Ambiguous document")

    assert result.document_type == DocumentType.UNKNOWN
    assert result.confidence == 0.79


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"document_type":"unsupported","confidence":0.9,"reason":"x"}',
        '{"document_type":"goal","confidence":1.5,"reason":"x"}',
        '{"document_type":"goal","confidence":0.9}',
    ],
)
async def test_rejects_invalid_llm_response(
    service: DocumentClassificationService,
    llm_service: AsyncMock,
    content: str,
):
    llm_service.generate.return_value = LLMResponse(content=content)

    with pytest.raises(
        DocumentClassificationError,
        match="invalid response",
    ):
        await service.classify("Annual goals")


async def test_wraps_provider_failure(
    service: DocumentClassificationService,
    llm_service: AsyncMock,
):
    llm_service.generate.side_effect = RuntimeError("provider secret")

    with pytest.raises(
        DocumentClassificationError,
        match="provider failed",
    ) as error:
        await service.classify("Annual goals")

    assert "provider secret" not in str(error.value)


async def test_rejects_empty_content(
    service: DocumentClassificationService,
    llm_service: AsyncMock,
):
    with pytest.raises(
        DocumentClassificationError,
        match="content is required",
    ):
        await service.classify("  ")

    llm_service.generate.assert_not_awaited()


def test_rejects_invalid_minimum_confidence(llm_service: AsyncMock):
    with pytest.raises(ValueError, match="between 0 and 1"):
        DocumentClassificationService(
            llm_service=llm_service,
            minimum_confidence=1.1,
        )