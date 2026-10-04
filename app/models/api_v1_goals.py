from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.goal import GoalScope, GoalStatus


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    source: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Target date cannot be before start date")
        return self


class GoalUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    scope: GoalScope | None = None
    start_date: date | None = None
    end_date: date | None = None
    source: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_update_field_and_validate_dates(self):
        if not self.model_fields_set:
            raise ValueError("At least one goal field must be provided")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Target date cannot be before start date")
        return self


class GoalResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus
    source: str | None = None
    created_at: datetime
    updated_at: datetime


class GoalExpectationStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    MET = "met"
    ABOVE = "above"


class GoalAssessmentResponse(BaseModel):
    goal_id: str
    expected_achievement_count: int = Field(ge=1)
    achievement_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    demonstrated_impact_count: int = Field(ge=0)
    qualifying_achievement_count: int = Field(ge=0)
    progress_percentage: int = Field(ge=0)
    status: GoalExpectationStatus
    description: str
