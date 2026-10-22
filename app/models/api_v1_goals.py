from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.goal import GoalScope, GoalStatus, GoalSubStatus


class GoalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    source: str | None = Field(default=None, max_length=100)
    source_document_id: str | None = None

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
    source_document_id: str | None = None

    @model_validator(mode="after")
    def require_update_field_and_validate_dates(self):
        if not self.model_fields_set:
            raise ValueError("At least one goal field must be provided")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Target date cannot be before start date")
        return self


class GoalDeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("A reason is required to deactivate a goal")
        return reason


class GoalReopenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("A reason is required to reopen a completed goal")
        return reason


class GoalResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus
    sub_status: GoalSubStatus = GoalSubStatus.NEEDS_REVIEW
    deactivation_reason: str | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime
    source_document_id: str | None = None


class GoalStatusHistoryResponse(BaseModel):
    id: str
    goal_id: str
    from_status: GoalStatus
    to_status: GoalStatus
    reason: str | None = None
    changed_by_user_id: str | None = None
    created_at: datetime


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


class GoalImportDuplicateResponse(BaseModel):
    title: str
    existing_goal_id: str


class GoalImportResponse(BaseModel):
    imported_goals: list[GoalResponse] = Field(default_factory=list)
    skipped_duplicates: list[GoalImportDuplicateResponse] = Field(default_factory=list)
