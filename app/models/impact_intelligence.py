from enum import Enum

from pydantic import BaseModel, Field

from app.models.document_chunk_embedding import KnowledgeSearchResult
from app.models.document_expectation import DocumentExpectation
from app.models.impact_assessment import ImpactType


class EvidenceSupportLevel(str, Enum):
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class EvidenceCandidate(BaseModel):
    """A semantically retrieved knowledge chunk considered as evidence."""

    expectation_id: str
    search_result: KnowledgeSearchResult


class EvidenceEvaluation(BaseModel):
    """Transient evaluation of whether a retrieved chunk supports an expectation."""

    candidate_chunk_id: str
    supports_expectation: bool
    support_level: EvidenceSupportLevel
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)


class ExpectationEvidenceResult(BaseModel):
    """Transient M4 result combining an expectation with retrieved evidence."""

    expectation: DocumentExpectation
    candidates: list[EvidenceCandidate] = Field(default_factory=list)
    evaluations: list[EvidenceEvaluation] = Field(default_factory=list)


class ImpactAssessmentEvaluation(BaseModel):
    """Transient LLM output used to create an ImpactAssessment."""

    impact_type: ImpactType
    impact_summary: str = Field(min_length=1)
    impact_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class CareerInsight(BaseModel):
    """Transient career-level synthesis of persisted impact assessments."""

    goal_id: str
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    impact_types: list[ImpactType] = Field(default_factory=list)
    supporting_assessment_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
