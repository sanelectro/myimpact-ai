from enum import Enum

from pydantic import BaseModel, Field


class ExpectationCategory(str, Enum):
    DELIVERY = "delivery"
    TECHNICAL_LEADERSHIP = "technical_leadership"
    ARCHITECTURE = "architecture"
    MENTORING = "mentoring"
    INNOVATION = "innovation"
    COLLABORATION = "collaboration"
    OPERATIONAL_EXCELLENCE = "operational_excellence"
    BUSINESS_DOMAIN_IMPACT = "business_domain_impact"


class ExpectationSourceReference(BaseModel):
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    text_span: str | None = None


class Expectation(BaseModel):
    category: ExpectationCategory
    description: str = Field(min_length=1)
    evidence_hints: list[str] = Field(default_factory=list)
    source_reference: ExpectationSourceReference | None = None
    confidence: float = Field(ge=0, le=1)


class ExpectationExtractionResult(BaseModel):
    expectations: list[Expectation] = Field(default_factory=list)
