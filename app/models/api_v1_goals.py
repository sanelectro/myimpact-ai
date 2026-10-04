from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.goal import GoalScope, GoalStatus


class GoalCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    source: str | None = None


class GoalUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus | None = None
    source: str | None = None

    @model_validator(mode="after")
    def require_update_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one goal field must be provided")
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
