from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.goals import _to_response
from app.db.session import get_db
from app.exceptions import LLMQuotaExceededError
from app.models.api_v1_goals import GoalImportResponse
from app.services.goal_import import GoalImportService
from app.services.llm.factory import create_llm_service
from app.storage.local import LocalFileStorage

router = APIRouter(prefix="/goals", tags=["goals"])


def get_goal_import_service(db: Annotated[Session, Depends(get_db)]) -> GoalImportService:
    return GoalImportService(
        session=db,
        storage=LocalFileStorage("storage/documents"),
        llm_service=create_llm_service(),
    )


@router.post("/import-from-document", response_model=GoalImportResponse, status_code=status.HTTP_201_CREATED)
async def import_goals_from_document(
    document_id: Annotated[str, Query(min_length=1)],
    user_id: Annotated[str, Query(min_length=1)],
    service: Annotated[GoalImportService, Depends(get_goal_import_service)],
) -> GoalImportResponse:
    try:
        result = await service.import_from_document(document_id, user_id)
    except LLMQuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return GoalImportResponse(
        imported_goals=[_to_response(goal) for goal in result["imported_goals"]],
        skipped_duplicates=result["skipped_duplicates"],
    )
