from datetime import date, datetime

from pydantic import BaseModel

from app.models.api_v1_goals import GoalResponse
from app.models.milestone import MilestoneStatus


class ArchivedEvidenceResponse(BaseModel):
    id: str
    title: str
    description: str | None
    source_type: str
    source_url: str | None
    captured_at: datetime
    archived_at: datetime
    goal_titles: list[str]


class ArchivedMilestoneResponse(BaseModel):
    id: str
    goal_id: str
    goal_title: str
    title: str
    description: str | None
    completion_criteria: str | None
    status: MilestoneStatus
    due_date: date | None
    archived_at: datetime


class ArchivesResponse(BaseModel):
    goals: list[GoalResponse]
    evidence: list[ArchivedEvidenceResponse]
    milestones: list[ArchivedMilestoneResponse]
