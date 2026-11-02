from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.llm import LLMRequest
from app.services.llm.groq_service import GroqLLMService, _GroqRequestLimiter
from app.services.llm.interface import ILLMService
from app.services.llm.mock_service import MockLLMService


def test_mock_llm_implements_interface():

    llm = MockLLMService()

    assert isinstance(llm, ILLMService)


async def test_mock_llm_generate():

    llm = MockLLMService()

    request = LLMRequest(
        prompt="What is MyImpact?"
    )

    response = await llm.generate(request)

    assert response.content == (
        "Mock response for: What is MyImpact?"
    )

    assert response.model == "mock-model"


async def test_groq_waits_for_rate_limit_slot_and_logs_wait(caplog):

    limiter = _GroqRequestLimiter()
    limiter._next_request_at = 100.0

    with patch(
        "app.services.llm.groq_service.time.monotonic",
        return_value=90.0,
    ), patch(
        "app.services.llm.groq_service.asyncio.sleep",
        new_callable=AsyncMock,
    ) as sleep, caplog.at_level("INFO"):
        await limiter.wait_for_slot(10.0)

    sleep.assert_awaited_once_with(10.0)
    assert "Groq request waiting for rate-limit slot" in caplog.text
    assert "wait_seconds=10.000" in caplog.text


@pytest.mark.asyncio
async def test_groq_service_uses_configured_interval():

    settings = SimpleNamespace(
        groq_api_key="test-key",
        groq_base_url="https://api.groq.com/openai/v1",
        groq_model="test-model",
        llm_timeout_seconds=60.0,
        llm_min_interval_seconds=3.0,
        groq_max_retries=0,
        groq_retry_base_seconds=2.0,
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))]
    )

    with patch(
        "app.services.llm.groq_service.get_settings",
        return_value=settings,
    ), patch(
        "app.services.llm.groq_service.AsyncOpenAI"
    ) as client_factory:
        client_factory.return_value.chat.completions.create = AsyncMock(
            return_value=response
        )
        service = GroqLLMService()
        result = await service.generate(LLMRequest(prompt="question"))

    assert result.content == "answer"
    assert result.model == "test-model"
    assert service.min_interval_seconds == 3.0
    client_factory.return_value.chat.completions.create.assert_awaited_once()