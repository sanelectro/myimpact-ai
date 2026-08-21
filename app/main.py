from fastapi import FastAPI

from app.models.chat import ChatRequest, ChatResponse
from app.models.llm import LLMRequest
from app.services.llm.factory import create_llm_service

app = FastAPI(
    title="MyImpact AI",
    description="AI intelligence and orchestration service for MyImpact",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "myimpact-ai",
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):

    llm = create_llm_service()

    llm_request = LLMRequest(
        prompt=request.message
    )

    response = await llm.generate(
        request=llm_request
    )

    return ChatResponse(
        response=response.content,
        model=response.model,
    )