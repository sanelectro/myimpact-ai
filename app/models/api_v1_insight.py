from datetime import datetime

from pydantic import BaseModel, Field

from app.models.impact_intelligence import CareerInsight
from app.models.impact_assessment import ImpactType


class GoalInsightResponse(CareerInsight):
    """Product-facing goal insight contract."""


class GoalReportResponse(BaseModel):
    """Product-facing, generated goal impact report."""

    goal_id: str
    goal_title: str
    generated_at: datetime
    headline: str
    summary: str
    impact_types: list[ImpactType] = Field(default_factory=list)
    supporting_assessment_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    impact_assessment_count: int = Field(ge=1)
