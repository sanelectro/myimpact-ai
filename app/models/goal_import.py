from datetime import date

from pydantic import BaseModel, Field

from app.models.goal import GoalScope


class GoalImportCandidate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    scope: GoalScope = GoalScope.PERSONAL
    start_date: date | None = None
    end_date: date | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class GoalImportExtractionResult(BaseModel):
    goals: list[GoalImportCandidate] = Field(default_factory=list)
