from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReportType(str, Enum):
    MONTHLY_IMPACT = "monthly_impact"
    QUARTERLY_IMPACT = "quarterly_impact"
    ANNUAL_PERFORMANCE = "annual_performance"
    GOAL_PROGRESS = "goal_progress"
    PROMOTION_EVIDENCE = "promotion_evidence"
    ONE_TO_ONE = "one_to_one"


class ReportStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    ARCHIVED = "archived"


class Report(BaseModel):
    id: str
    user_id: str
    report_type: ReportType
    period_start: date
    period_end: date
    content: str
    version: int = Field(default=1, ge=1)
    status: ReportStatus = ReportStatus.CURRENT
    generated_at: datetime
    updated_at: datetime
