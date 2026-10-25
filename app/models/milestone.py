from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class MilestoneStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class MilestoneSource(str, Enum):
    AI = "ai"
    MANUAL = "manual"


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    completion_criteria: str | None = Field(default=None, max_length=5000)
    status: MilestoneStatus = MilestoneStatus.NOT_STARTED
    due_date: date | None = None
    source: MilestoneSource = MilestoneSource.MANUAL

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Milestone title cannot be blank")
        return title


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    completion_criteria: str | None = Field(default=None, max_length=5000)
    status: MilestoneStatus | None = None
    due_date: date | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Milestone title cannot be blank")
        title = value.strip()
        if not title:
            raise ValueError("Milestone title cannot be blank")
        return title

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: MilestoneStatus | None) -> MilestoneStatus:
        if value is None:
            raise ValueError("Milestone status cannot be blank")
        return value


class MilestoneResponse(BaseModel):
    id: str
    goal_id: str
    title: str
    description: str | None = None
    completion_criteria: str | None = None
    status: MilestoneStatus
    source: MilestoneSource = MilestoneSource.MANUAL
    due_date: date | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MilestoneSuggestion(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=5000)
    completion_criteria: str = Field(min_length=1, max_length=5000)

    @field_validator("title", "description", "completion_criteria")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Milestone suggestion text cannot be blank")
        return text


class MilestoneSuggestionsResponse(BaseModel):
    suggestions: list[MilestoneSuggestion] = Field(min_length=1, max_length=5)
