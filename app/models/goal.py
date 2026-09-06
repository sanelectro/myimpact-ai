from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class GoalStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Goal(BaseModel):
    id: str
    user_id: str
    title: str = Field(min_length=1)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    source: str | None = None
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    user_id: str
    title: str = Field(min_length=1)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    source: str | None = None
