import hashlib
import math

from app.models.embedding import EmbeddingRequest, EmbeddingResponse
from app.services.embedding.interface import IEmbeddingService


class MockEmbeddingService(IEmbeddingService):
    """Deterministic local embedding provider for tests and development."""

    def __init__(self, dimensions: int = 8):
        if dimensions < 1:
            raise ValueError("Embedding dimensions must be greater than zero")

        self.dimensions = dimensions

    async def embed(
        self,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        return EmbeddingResponse(
            embeddings=[self._embed_text(text) for text in request.inputs],
            model="mock-embedding",
        )

    def _embed_text(self, text: str) -> list[float]:
        values: list[float] = []
        counter = 0

        while len(values) < self.dimensions:
            digest = hashlib.sha256(
                f"{counter}:{text}".encode("utf-8")
            ).digest()

            for offset in range(0, len(digest), 4):
                if len(values) >= self.dimensions:
                    break

                raw = int.from_bytes(
                    digest[offset : offset + 4],
                    byteorder="big",
                    signed=False,
                )
                values.append((raw / 2**32) * 2 - 1)

            counter += 1

        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0:
            return values

        return [value / norm for value in values]
