import logging

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.document import router as documents_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.evidence_mapping import router as evidence_mapping_router
from app.api.routes.evidence_version import router as evidence_version_router
from app.api.routes.goals import router as goals_router
from app.api.routes.health import router as health_router
from app.api.routes.impact_assessment import router as impact_assessment_router
from app.api.routes.report import router as report_router
from app.api.routes.users import router as users_router
from app.api.v1.errors import (
    handle_v1_http_exception,
    handle_v1_unhandled_exception,
    handle_v1_validation_error,
)
from app.api.v1.router import router as api_v1_router
from app.api.v1.integrations import oauth_callback_router
from app.auth import authorize_request_user
from app.config.settings import get_settings
from app.models.chat import ChatRequest, ChatResponse
from app.models.llm import LLMRequest
from app.services.llm.factory import create_llm_service

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="MyImpact AI",
    description="AI intelligence and orchestration service for MyImpact",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in get_settings().allowed_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
auth_dependency = [Depends(authorize_request_user)]
app.include_router(api_v1_router, dependencies=auth_dependency)
app.include_router(oauth_callback_router)

app.add_exception_handler(StarletteHTTPException, handle_v1_http_exception)
app.add_exception_handler(RequestValidationError, handle_v1_validation_error)
app.add_exception_handler(Exception, handle_v1_unhandled_exception)
app.include_router(users_router, dependencies=auth_dependency)
app.include_router(goals_router, dependencies=auth_dependency)
app.include_router(evidence_router, dependencies=auth_dependency)
app.include_router(evidence_version_router, dependencies=auth_dependency)
app.include_router(evidence_mapping_router, dependencies=auth_dependency)
app.include_router(impact_assessment_router, dependencies=auth_dependency)
app.include_router(report_router, dependencies=auth_dependency)
app.include_router(documents_router, dependencies=auth_dependency)

@app.post("/chat", response_model=ChatResponse, dependencies=auth_dependency)
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