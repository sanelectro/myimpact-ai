from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.session import get_db
from app.services.evidence_discovery import discover_evidence
from app.services.goal import GoalService
from app.services.milestone import MilestoneService
from app.services.source_connections import (
    SUPPORTED_PROVIDERS,
    SourceConnectionError,
    complete_oauth,
    disconnect_source,
    get_authorization_url,
    get_connection_status,
)

router = APIRouter(prefix="/integrations", tags=["source-integrations"])
oauth_callback_router = APIRouter(tags=["source-integrations"])


class SourceConnectResponse(BaseModel):
    authorization_url: str


class SourceConnectionResponse(BaseModel):
    provider: str
    connected: bool
    account: str
    managed_locally: bool = False


class EvidenceDiscoveryRequest(BaseModel):
    start_date: date
    end_date: date
    sources: list[Literal["github", "jira"]] = Field(min_length=1)
    milestone_id: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date.")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("Evidence discovery is limited to a 12-month range.")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("Each evidence source can only be selected once.")
        return self


class DiscoveredEvidence(BaseModel):
    id: str
    source_type: Literal["github", "jira"]
    source_id: str
    title: str
    description: str | None
    source_url: str | None
    captured_at: datetime
    source_updated_at: datetime | None = None
    summary: str
    relevance: Literal["high", "medium", "low"]
    repository: str | None = None
    status: str | None = None
    issue_type: str | None = None
    jira_keys: list[str] = Field(default_factory=list)


def _get_services(db: Session) -> tuple[GoalService, MilestoneService]:
    return GoalService(db), MilestoneService(db)


@router.get("/connections", response_model=list[SourceConnectionResponse])
def list_connections(
    user_id: Annotated[str, Query(min_length=1)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SourceConnectionResponse]:
    try:
        return [
            SourceConnectionResponse(**item)
            for item in get_connection_status(db, user_id)
        ]
    except SourceConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/{provider}/authorize", response_model=SourceConnectResponse)
def authorize_source(
    provider: str,
    goal_id: Annotated[str, Query(min_length=1)],
    user_id: Annotated[str, Query(min_length=1)],
    db: Annotated[Session, Depends(get_db)],
) -> SourceConnectResponse:
    goal = GoalService(db).get_goal_by_id(goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    if getattr(goal.status, "value", goal.status) != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only active goals can accept new evidence.",
        )
    try:
        return SourceConnectResponse(
            authorization_url=get_authorization_url(provider, user_id, goal_id)
        )
    except SourceConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    provider: str,
    user_id: Annotated[str, Query(min_length=1)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    try:
        disconnect_source(db, user_id, provider)
    except SourceConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/goals/{goal_id}/evidence-discovery",
    response_model=list[DiscoveredEvidence],
)
async def discover_goal_evidence(
    goal_id: str,
    request: EvidenceDiscoveryRequest,
    user_id: Annotated[str, Query(min_length=1)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DiscoveredEvidence]:
    goal_service, milestone_service = _get_services(db)
    goal = goal_service.get_goal_by_id(goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    if getattr(goal.status, "value", goal.status) != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only active goals can accept new evidence.",
        )

    milestone_title = None
    milestone_description = None
    if request.milestone_id:
        milestone = milestone_service.get_milestone_by_id_and_goal(
            request.milestone_id,
            goal_id,
        )
        if milestone is None or milestone.archived_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Milestone not found for this goal.",
            )
        milestone_title = milestone.title
        milestone_description = " ".join(
            part
            for part in (milestone.description, milestone.completion_criteria)
            if part
        )

    try:
        results = await discover_evidence(
            session=db,
            user_id=user_id,
            goal_title=goal.title,
            goal_description=goal.description,
            milestone_title=milestone_title,
            milestone_description=milestone_description,
            start_date=request.start_date,
            end_date=request.end_date,
            sources=request.sources,
        )
    except SourceConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return [DiscoveredEvidence(**item) for item in results]


@oauth_callback_router.get("/api/v1/integrations/oauth/callback/{provider}")
def source_oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    web_url = settings.source_integrations_web_url.rstrip("/")
    goal_id = ""
    connected = False
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown source.")
    if not error and code and state:
        try:
            _, goal_id = complete_oauth(db, provider, code, state)
            connected = True
        except SourceConnectionError:
            connected = False
    params = (
        {"source_connected": provider}
        if connected
        else {"source_error": provider}
    )
    suffix = f"/goals/{quote(goal_id, safe='')}" if goal_id else "/goals"
    return RedirectResponse(
        f"{web_url}{suffix}?{urlencode(params)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
