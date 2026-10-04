from datetime import datetime

from pydantic import BaseModel, Field

from app.models.impact_assessment import ImpactType
from app.models.impact_intelligence import CareerInsight


class GoalEvidenceResponse(BaseModel):
    evidence_id: str
    title: str
    description: str | None = None
    source_type: str
    captured_at: datetime
    relevance: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str | None = None


class ImpactAnalysisRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    discovery_limit: int = Field(default=5, ge=1, le=20)


class ImpactAnalysisResponse(BaseModel):
    goal_id: str
    processed_expectations: int
    discovered_candidates: int
    evaluated_candidates: int
    persisted_evidence_count: int
    impact_assessment_count: int
    career_insight: CareerInsight


class ImpactAssessmentResponse(BaseModel):
    id: str
    evidence_id: str
    goal_id: str
    impact_type: ImpactType
    impact_summary: str
    impact_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    assessment_version: int
    created_at: datetime
    updated_at: datetime
