from fastapi import FastAPI

from app.api.routes.evidence import router as evidence_router
from app.api.routes.evidence_mapping import router as evidence_mapping_router
from app.api.routes.evidence_version import router as evidence_version_router
from app.api.routes.goals import router as goals_router
from app.api.routes.health import router as health_router
from app.api.routes.impact_assessment import router as impact_assessment_router
from app.api.routes.report import router as report_router
from app.api.routes.users import router as users_router
from app.models.chat import ChatRequest, ChatResponse
from app.models.llm import LLMRequest
from app.services.llm.factory import create_llm_service

app = FastAPI(
    title="MyImpact AI",
    description="AI intelligence and orchestration service for MyImpact",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(users_router)
app.include_router(goals_router)
app.include_router(evidence_router)
app.include_router(evidence_version_router)
app.include_router(evidence_mapping_router)
app.include_router(impact_assessment_router)
app.include_router(report_router)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    llm = create_llm_service()

    llm_request = LLMRequest(
        prompt=request.message,
    )

    response = await llm.generate(
        request=llm_request,
    )

    return ChatResponse(
        response=response.content,
        model=response.model,
    )