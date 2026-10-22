from enum import Enum

from pydantic import BaseModel, Field, model_validator


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

    @model_validator(mode="before")
    @classmethod
    def normalize_source_reference(cls, value):
        if isinstance(value, dict):
            value = value.copy()
            source_reference = value.get("source_reference")
            if isinstance(source_reference, str):
                value["source_reference"] = {"text_span": source_reference}

            evidence_hints = value.get("evidence_hints")
            if isinstance(evidence_hints, str):
                value["evidence_hints"] = [evidence_hints]
            elif evidence_hints is None:
                value["evidence_hints"] = []

        return value


class ExpectationExtractionResult(BaseModel):
    expectations: list[Expectation] = Field(default_factory=list)
