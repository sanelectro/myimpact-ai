from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EvidenceRelevance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceMapping(BaseModel):
    id: str
    evidence_id: str
    goal_id: str
    relevance: EvidenceRelevance
    reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
