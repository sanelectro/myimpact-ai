from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ImpactType(str, Enum):
    TECHNICAL = "technical"
    BUSINESS = "business"
    CUSTOMER = "customer"
    RELIABILITY = "reliability"
    PERFORMANCE = "performance"
    AUTOMATION = "automation"
    LEADERSHIP = "leadership"
    MENTORING = "mentoring"
    INNOVATION = "innovation"
    OPERATIONAL = "operational"


class ImpactAssessment(BaseModel):
    id: str
    evidence_id: str
    goal_id: str
    impact_type: ImpactType
    impact_summary: str
    impact_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    assessment_version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime
