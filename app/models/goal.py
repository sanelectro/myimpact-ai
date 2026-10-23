from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class GoalScope(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    ORGANIZATION = "organization"


class GoalStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class GoalSubStatus(str, Enum):
    NEEDS_REVIEW = "needs_review"
    READY_FOR_APPROVAL = "ready_for_approval"
    NOT_STARTED = "not_started"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OFF_TRACK = "off_track"
    COMPLETED = "completed"
    NONE = "none"


DEFAULT_SUB_STATUS_BY_GOAL_STATUS = {
    GoalStatus.DRAFT: GoalSubStatus.NEEDS_REVIEW,
    GoalStatus.APPROVED: GoalSubStatus.NOT_STARTED,
    GoalStatus.ACTIVE: GoalSubStatus.ON_TRACK,
    GoalStatus.COMPLETED: GoalSubStatus.COMPLETED,
    GoalStatus.ARCHIVED: GoalSubStatus.NONE,
}

VALID_SUB_STATUSES_BY_GOAL_STATUS = {
    GoalStatus.DRAFT: {GoalSubStatus.NEEDS_REVIEW, GoalSubStatus.READY_FOR_APPROVAL},
    GoalStatus.APPROVED: {GoalSubStatus.NOT_STARTED},
    GoalStatus.ACTIVE: {GoalSubStatus.ON_TRACK, GoalSubStatus.AT_RISK, GoalSubStatus.OFF_TRACK},
    GoalStatus.COMPLETED: {GoalSubStatus.COMPLETED},
    GoalStatus.ARCHIVED: {GoalSubStatus.NONE},
}


class Goal(BaseModel):
    id: str
    user_id: str
    title: str = Field(min_length=1)
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus = GoalStatus.DRAFT
    sub_status: GoalSubStatus = GoalSubStatus.NEEDS_REVIEW
    deactivation_reason: str | None = None
    source: str | None = None
    source_document_id: str | None = None
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    user_id: str
    title: str = Field(min_length=1)
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus = GoalStatus.DRAFT
    sub_status: GoalSubStatus | None = None
    source: str | None = None
    source_document_id: str | None = None

    @model_validator(mode="after")
    def validate_lifecycle_pair(self):
        if self.sub_status is None:
            self.sub_status = DEFAULT_SUB_STATUS_BY_GOAL_STATUS[self.status]
        elif self.sub_status not in VALID_SUB_STATUSES_BY_GOAL_STATUS[self.status]:
            raise ValueError("Invalid goal status/sub-status combination")
        return self
