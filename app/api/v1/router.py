from fastapi import APIRouter
from pydantic import BaseModel


class ApiV1Info(BaseModel):
    name: str
    version: str
    status: str


router = APIRouter(prefix="/api/v1", tags=["api-v1"])


@router.get("", response_model=ApiV1Info)
def get_api_v1_info() -> ApiV1Info:
    return ApiV1Info(
        name="MyImpact AI API",
        version="v1",
        status="available",
    )
