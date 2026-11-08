from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.goal import GoalScope, GoalStructuredFields


class GoalValidationStatus(str, Enum):
    READY = "READY"
    NEEDS_REFINEMENT = "NEEDS_REFINEMENT"
    NEEDS_DISCUSSION = "NEEDS_DISCUSSION"
    INVALID = "INVALID"

    @classmethod
    def _missing_(cls, value: object) -> "GoalValidationStatus | None":
        if value == "NEEDS_IMPROVEMENT":
            return cls.NEEDS_REFINEMENT
        if value == "NEEDS_REVIEW":
            return cls.NEEDS_DISCUSSION
        return None


class GoalValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class GoalValidationDimension(str, Enum):
    STRUCTURE = "structure"
    ACCOUNTABILITY = "accountability"
    SUCCESS_CRITERIA = "success_criteria"
    DELIVERABLES = "deliverables"
    MEASUREMENT = "measurement"
    TIMEFRAME = "timeframe"
    SCOPE = "scope"
    OUTCOME_IMPACT = "outcome_impact"
    ROLE_ALIGNMENT = "role_alignment"


class GoalValidationFindingCode(str, Enum):
    MISSING_TITLE = "missing_title"
    MISSING_ACCOUNTABILITY = "missing_accountability"
    MISSING_SUCCESS_CRITERIA = "missing_success_criteria"
    MISSING_DELIVERABLES = "missing_deliverables"
    INCONSISTENT_TIMEFRAME = "inconsistent_timeframe"
    INCOMPLETE_MEASUREMENT_CONTEXT = "incomplete_measurement_context"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    AMBIGUOUS_ACCOUNTABILITY = "ambiguous_accountability"
    AMBIGUOUS_SUCCESS_CRITERIA = "ambiguous_success_criteria"
    CONFLICTING_DETAILS = "conflicting_details"
    AMBIGUOUS_TIMEFRAME = "ambiguous_timeframe"
    AMBIGUOUS_SCOPE = "ambiguous_scope"
    AMBIGUOUS_MEASUREMENT = "ambiguous_measurement"
    MIXED_ACCOUNTABILITY = "mixed_accountability"
    FEASIBILITY_NEEDS_CONTEXT = "feasibility_needs_context"
    ROLE_ALIGNMENT_NEEDS_CONTEXT = "role_alignment_needs_context"


class GoalSemanticIssueCode(str, Enum):
    AMBIGUOUS_INTENT = "ambiguous_intent"
    AMBIGUOUS_ACCOUNTABILITY = "ambiguous_accountability"
    AMBIGUOUS_SUCCESS_CRITERIA = "ambiguous_success_criteria"
    CONFLICTING_DETAILS = "conflicting_details"
    AMBIGUOUS_TIMEFRAME = "ambiguous_timeframe"
    AMBIGUOUS_SCOPE = "ambiguous_scope"
    AMBIGUOUS_MEASUREMENT = "ambiguous_measurement"
    MIXED_ACCOUNTABILITY = "mixed_accountability"
    FEASIBILITY_NEEDS_CONTEXT = "feasibility_needs_context"
    ROLE_ALIGNMENT_NEEDS_CONTEXT = "role_alignment_needs_context"


class GoalSemanticSourceField(str, Enum):
    TITLE = "title"
    DESCRIPTION = "description"
    GOAL_TYPE = "goal_type"
    ACCOUNTABILITY = "accountability"
    SUCCESS_CRITERIA = "success_criteria"
    DELIVERABLES = "deliverables"
    OUTCOME = "outcome"
    IMPACT = "impact"
    MEASUREMENT = "measurement"
    BASELINE = "baseline"
    TARGET = "target"
    TIMEFRAME = "timeframe"
    DEPENDENCIES = "dependencies"
    ROLE_ALIGNMENT = "role_alignment"
    SOURCE = "source"
    SCOPE = "scope"


class GoalSemanticEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    field: GoalSemanticSourceField
    quote: str = Field(min_length=1)


class GoalSemanticIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: GoalSemanticIssueCode
    evidence: list[GoalSemanticEvidence] = Field(min_length=1, max_length=5)


class GoalSemanticAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    issues: list[GoalSemanticIssue] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def unique_issue_codes(self):
        codes = [issue.code for issue in self.issues]
        if len(codes) != len(set(codes)):
            raise ValueError("Semantic issue codes must be unique")
        return self


class GoalValidationTimeframe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date | None = None
    end_date: date | None = None


class GoalValidationInput(GoalStructuredFields):
    """Structured goal context used for deterministic and semantic validation."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    scope: GoalScope | None = None
    timeframe: GoalValidationTimeframe | None = None
    source: str | None = None
    source_document_id: str | None = None

    @field_validator(
        "title",
        "description",
        "source",
        "source_document_id",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class GoalValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: GoalValidationDimension
    finding_code: GoalValidationFindingCode
    severity: GoalValidationSeverity
    validation_status: GoalValidationStatus
    explanation: str = Field(min_length=1)
    missing_info: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    suggested_improvement: str | None = None
    human_intervention_required: bool = False


class GoalValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GoalValidationStatus
    findings: list[GoalValidationFinding] = Field(default_factory=list)

    @classmethod
    def from_findings(
        cls, findings: list[GoalValidationFinding]
    ) -> "GoalValidationResult":
        priority = {
            GoalValidationStatus.READY: 0,
            GoalValidationStatus.NEEDS_REFINEMENT: 1,
            GoalValidationStatus.NEEDS_DISCUSSION: 2,
            GoalValidationStatus.INVALID: 3,
        }
        status = max(
            (finding.validation_status for finding in findings),
            key=priority.__getitem__,
            default=GoalValidationStatus.READY,
        )
        return cls(status=status, findings=findings)

    @model_validator(mode="after")
    def status_matches_findings(self):
        priority = {
            GoalValidationStatus.READY: 0,
            GoalValidationStatus.NEEDS_REFINEMENT: 1,
            GoalValidationStatus.NEEDS_DISCUSSION: 2,
            GoalValidationStatus.INVALID: 3,
        }
        expected_status = max(
            (finding.validation_status for finding in self.findings),
            key=priority.__getitem__,
            default=GoalValidationStatus.READY,
        )
        if self.status != expected_status:
            raise ValueError("Validation result status must match its findings")
        return self
