from fastapi import APIRouter
from pydantic import BaseModel

from app.api.v1.goals import router as goals_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.expectations import router as expectations_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.impact import router as impact_router


class ApiV1Info(BaseModel):
    name: str
    version: str
    status: str


router = APIRouter(prefix="/api/v1", tags=["api-v1"])


@router.get("", response_model=ApiV1Info)
def get_api_v1_info() -> ApiV1Info:
    return ApiV1Info(name="MyImpact AI API", version="v1", status="available")


router.include_router(knowledge_router)
router.include_router(expectations_router)
router.include_router(goals_router)
router.include_router(evidence_router)
router.include_router(impact_router)
