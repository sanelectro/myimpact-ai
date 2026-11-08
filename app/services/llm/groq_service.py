import asyncio
import logging
import time

from openai import AsyncOpenAI, RateLimitError

from app.config.settings import get_settings
from app.models.llm import LLMRequest, LLMResponse
from app.services.llm.interface import ILLMService

logger = logging.getLogger(__name__)


class _GroqRequestLimiter:

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._next_request_at = 0.0

    async def wait_for_slot(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_request_at - now)
            self._next_request_at = (
                max(now, self._next_request_at) + interval_seconds
            )

        if wait_seconds > 0:
            logger.info(
                "Groq request waiting for rate-limit slot: wait_seconds=%.3f "
                "interval_seconds=%.3f",
                wait_seconds,
                interval_seconds,
            )
            await asyncio.sleep(wait_seconds)


_request_limiter = _GroqRequestLimiter()


class GroqLLMService(ILLMService):

    def __init__(self):

        settings = get_settings()

        self.client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

        self.model = settings.groq_model
        self.min_interval_seconds = settings.llm_min_interval_seconds
        self.max_retries = settings.groq_max_retries
        self.retry_base_seconds = settings.groq_retry_base_seconds

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        options = (
            {"response_format": request.response_format}
            if request.response_format is not None
            else {}
        )
        for attempt in range(self.max_retries + 1):
            await _request_limiter.wait_for_slot(
                self.min_interval_seconds
            )
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "user",
                            "content": request.prompt,
                        }
                    ],
                    **options,
                )
            except RateLimitError:
                if attempt >= self.max_retries:
                    logger.error(
                        "Groq rate limit exhausted after %d attempts",
                        attempt + 1,
                    )
                    raise

                retry_wait_seconds = self.retry_base_seconds * (2**attempt)
                logger.warning(
                    "Groq rate limit response; retrying: attempt=%d "
                    "max_attempts=%d wait_seconds=%.3f",
                    attempt + 1,
                    self.max_retries + 1,
                    retry_wait_seconds,
                )
                await asyncio.sleep(retry_wait_seconds)
            else:
                break

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=self.model,
            provider="groq",
        )