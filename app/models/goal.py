from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.goal_criteria import GoalCriterionDefinition


class GoalScope(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"
    ORGANIZATION = "organization"


class GoalLevel(str, Enum):
    ANNUAL = "ANNUAL"
    QUARTERLY = "QUARTERLY"
    MONTHLY = "MONTHLY"
    SPRINT = "SPRINT"


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


class GoalStructuredFields(BaseModel):
    """Optional typed goal definition details, separate from lifecycle state."""

    model_config = ConfigDict(extra="forbid")

    goal_type: str | None = Field(default=None, max_length=100)
    accountability: str | None = Field(default=None, max_length=1000)
    success_criteria: list[GoalCriterionDefinition] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    outcome: str | None = Field(default=None, max_length=4000)
    impact: str | None = Field(default=None, max_length=4000)
    measurement: str | None = Field(default=None, max_length=1000)
    baseline: str | None = Field(default=None, max_length=1000)
    target: str | None = Field(default=None, max_length=1000)
    dependencies: list[str] = Field(default_factory=list)
    role_alignment: str | None = Field(default=None, max_length=2000)

    @field_validator(
        "goal_type",
        "accountability",
        "outcome",
        "impact",
        "measurement",
        "baseline",
        "target",
        "role_alignment",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("deliverables", "dependencies")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("List entries cannot be blank")
        return normalized


class Goal(BaseModel):
    id: str
    user_id: str
    title: str = Field(min_length=1)
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    goal_level: GoalLevel | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus = GoalStatus.DRAFT
    sub_status: GoalSubStatus = GoalSubStatus.NEEDS_REVIEW
    deactivation_reason: str | None = None
    source: str | None = None
    source_document_id: str | None = None
    structured_fields: GoalStructuredFields = Field(default_factory=GoalStructuredFields)
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    user_id: str
    title: str = Field(min_length=1)
    description: str | None = None
    scope: GoalScope = GoalScope.PERSONAL
    goal_level: GoalLevel | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus = GoalStatus.DRAFT
    sub_status: GoalSubStatus | None = None
    source: str | None = None
    source_document_id: str | None = None
    structured_fields: GoalStructuredFields = Field(default_factory=GoalStructuredFields)

    @model_validator(mode="after")
    def validate_lifecycle_pair(self):
        if self.sub_status is None:
            self.sub_status = DEFAULT_SUB_STATUS_BY_GOAL_STATUS[self.status]
        elif self.sub_status not in VALID_SUB_STATUSES_BY_GOAL_STATUS[self.status]:
            raise ValueError("Invalid goal status/sub-status combination")
        return self
