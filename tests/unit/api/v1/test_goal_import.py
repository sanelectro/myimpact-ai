from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.v1.goal_import import get_goal_import_service
from app.exceptions import LLMQuotaExceededError
from app.main import app

client = TestClient(app)


def test_goal_import_returns_clear_quota_error():
    service = MagicMock()
    service.import_from_document = AsyncMock(
        side_effect=LLMQuotaExceededError(
            "The LLM provider quota or token balance is exhausted. "
            "Check provider usage and billing limits, then retry."
        )
    )
    app.dependency_overrides[get_goal_import_service] = lambda: service
    try:
        response = client.post(
            "/api/v1/goals/import-from-document",
            params={"document_id": "doc-1", "user_id": "user-3"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "quota or token balance is exhausted" in response.json()["error"]["message"]