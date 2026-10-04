from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.models.api_v1_chat import ChatRequest, ChatResponse
from app.services.chat import ChatService
from app.services.llm.factory import create_llm_service

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_service() -> ChatService:
    return ChatService(create_llm_service())


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: Annotated[str, Query(min_length=1)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    # user_id is retained at the product boundary until authentication is introduced.
    # It is intentionally not forwarded to the LLM in this stateless milestone.
    return await chat_service.respond(request.message)
