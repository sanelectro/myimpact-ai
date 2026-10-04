from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.chat import get_chat_service, router
from app.main import app as main_app
from app.models.api_v1_chat import ChatResponse
from app.services.chat import ChatService
from app.models.llm import LLMResponse


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    yield TestClient(app)


def test_chat_returns_product_contract(client):
    llm = AsyncMock()
    llm.generate.return_value = LLMResponse(
        content="Focus on measurable impact.",
        model="mock-model",
    )
    service = ChatService(llm)
    client.app.dependency_overrides[get_chat_service] = lambda: service

    response = client.post(
        "/api/v1/chat?user_id=user-1",
        json={"message": "How should I prepare for my 1:1?"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Focus on measurable impact."}
    assert "model" not in response.json()
    llm.generate.assert_awaited_once()


def test_chat_requires_user_id(client):
    response = client.post(
        "/api/v1/chat",
        json={"message": "Hello"},
    )

    assert response.status_code == 422


def test_chat_rejects_empty_message(client):
    response = client.post(
        "/api/v1/chat?user_id=user-1",
        json={"message": ""},
    )

    assert response.status_code == 422


def test_chat_strips_message_before_sending_to_llm(client):
    llm = AsyncMock()
    llm.generate.return_value = LLMResponse(
        content="Hello",
        model="mock-model",
    )
    service = ChatService(llm)
    client.app.dependency_overrides[get_chat_service] = lambda: service

    response = client.post(
        "/api/v1/chat?user_id=user-1",
        json={"message": "  Hello  "},
    )

    assert response.status_code == 200
    assert llm.generate.await_args.kwargs["request"].prompt == "Hello"


def test_chat_service_rejects_whitespace_only_message():
    llm = AsyncMock()
    service = ChatService(llm)

    with pytest.raises(ValueError):
        # LLMRequest enforces a non-empty prompt after trimming.
        import asyncio
        asyncio.run(service.respond("   "))


def test_chat_router_is_mounted_on_main_app():
    paths = main_app.openapi()["paths"]
    assert "/api/v1/chat" in paths
