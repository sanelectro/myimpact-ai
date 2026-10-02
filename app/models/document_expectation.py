from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.expectation import ExpectationCategory


class DocumentExpectation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    category: ExpectationCategory
    description: str = Field(min_length=1)
    evidence_hints: list[str] = Field(default_factory=list)
    source_page: int | None = Field(default=None, ge=1)
    source_section: str | None = None
    source_text_span: str | None = None
    confidence: float = Field(ge=0, le=1)
    created_at: datetime
    updated_at: datetime