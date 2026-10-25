from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GoalCriterionType(str, Enum):
    BINARY = "BINARY"
    MILESTONE_BASED = "MILESTONE_BASED"
    MEASURABLE_TARGET = "MEASURABLE_TARGET"


class GoalCriterionApprovalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"


class GoalCriterionResult(str, Enum):
    NOT_ASSESSED = "NOT_ASSESSED"
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    MET = "MET"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class GoalAssessmentLifecycle(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    OBSOLETE = "OBSOLETE"


class GoalAssessmentRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class GoalSourceRetrievalStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class GoalAssessmentFeedbackType(str, Enum):
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    CHALLENGED = "CHALLENGED"


class GoalCriterionMilestone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    completion_conditions: str = Field(min_length=1, max_length=2000)


class GoalCriterionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_type: GoalCriterionType
    description: str = Field(min_length=1, max_length=2000)
    completion_conditions: str | None = Field(default=None, max_length=4000)
    milestones: list[GoalCriterionMilestone] = Field(default_factory=list, max_length=20)
    target_value: float | None = None
    unit: str | None = Field(default=None, max_length=100)
    evidence_suggestions: list[str] = Field(default_factory=list, max_length=20)
    assumptions_and_clarifications: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_type_definition(self):
        if self.criterion_type == GoalCriterionType.BINARY and not self.completion_conditions:
            raise ValueError("Binary criteria require completion conditions")
        if self.criterion_type == GoalCriterionType.MILESTONE_BASED:
            if not self.milestones:
                raise ValueError("Milestone-based criteria require at least one milestone")
            milestone_ids = [milestone.id for milestone in self.milestones]
            if len(milestone_ids) != len(set(milestone_ids)):
                raise ValueError("Milestone identifiers must be unique within a criterion")
        if self.criterion_type == GoalCriterionType.MEASURABLE_TARGET:
            if self.target_value is None or self.target_value <= 0:
                raise ValueError("Measurable targets must be greater than zero")
            if not self.unit:
                raise ValueError("Measurable targets require a unit")
            if not self.completion_conditions:
                raise ValueError("Measurable targets require completion conditions")
        if self.criterion_type != GoalCriterionType.MILESTONE_BASED and self.milestones:
            raise ValueError("Only milestone-based criteria may define milestones")
        if self.criterion_type != GoalCriterionType.MEASURABLE_TARGET and self.target_value is not None:
            raise ValueError("Only measurable-target criteria may define a target value")
        return self


class GoalCriterionProposal(GoalCriterionDefinition):
    pass


class GoalCriteriaGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[GoalCriterionProposal] = Field(min_length=1, max_length=12)


class GoalCriterionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: GoalCriterionDefinition


class GoalCriterionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: GoalCriterionDefinition


class GoalCriterionVersionResponse(BaseModel):
    id: str
    criterion_id: str
    version: int
    definition: GoalCriterionDefinition
    approval_status: GoalCriterionApprovalStatus
    created_by_user_id: str
    prompt_version: str | None
    model_version: str | None
    created_at: datetime
    approved_by_user_id: str | None
    approved_at: datetime | None


class GoalCriterionResponse(BaseModel):
    id: str
    goal_id: str
    current_version: int | None
    is_retired: bool
    created_at: datetime
    updated_at: datetime
    versions: list[GoalCriterionVersionResponse]


class GoalCriterionEvidenceResponse(BaseModel):
    id: str
    evidence_mapping_id: str
    evidence_id: str
    title: str
    source_url: str | None
    captured_at: datetime
    source_updated_at: datetime | None
    review_state: str | None
    source_validity: str
    relationship_type: str
    citation_excerpt: str | None


class GoalCriterionAssessmentEventResponse(BaseModel):
    id: str
    event_type: str
    lifecycle_state: GoalAssessmentLifecycle | None
    actor_user_id: str | None
    details: dict
    created_at: datetime


class GoalCriterionAssessmentResponse(BaseModel):
    id: str
    run_id: str
    criterion_id: str
    criterion_version_id: str
    criterion_version: int
    result: GoalCriterionResult
    lifecycle_state: GoalAssessmentLifecycle
    progress_percentage: int | None
    rationale: str
    confidence: float
    input_fingerprint: str
    model_version: str | None
    prompt_version: str
    created_at: datetime
    evidence: list[GoalCriterionEvidenceResponse]
    events: list[GoalCriterionAssessmentEventResponse]


class GoalCriterionSummary(BaseModel):
    criterion_id: str
    criterion_version: int | None
    result: GoalCriterionResult
    lifecycle_state: GoalAssessmentLifecycle | None
    progress_percentage: int | None
    assessment: GoalCriterionAssessmentResponse | None


class GoalAssessmentSummaryResponse(BaseModel):
    goal_id: str
    run_id: str | None
    run_status: GoalAssessmentRunStatus | None
    run_error_message: str | None = None
    criteria_count: int
    assessed_criteria_count: int
    criteria_met_count: int
    criteria_met_percentage: int | None
    goal_progress_percentage: int | None
    evidence_coverage_percentage: int | None
    average_confidence: float | None
    criteria: list[GoalCriterionSummary]
    source_retrieval_history: list["GoalSourceRetrievalResponse"] = Field(default_factory=list)
    updated_at: datetime | None


class GoalSourceRetrievalResponse(BaseModel):
    id: str
    goal_id: str
    run_id: str
    provider: str
    status: GoalSourceRetrievalStatus
    checked_at: datetime
    failure_reason: str | None
    used_snapshot: bool
    snapshot_captured_at: datetime | None


class GoalAssessmentRunResponse(BaseModel):
    id: str
    batch_id: str | None
    goal_id: str
    status: GoalAssessmentRunStatus
    trigger: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class GoalAssessmentBatchResponse(BaseModel):
    batch_id: str
    runs: list[GoalAssessmentRunResponse]


class GoalAssessmentBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal_ids: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_goals(self):
        if len(self.goal_ids) != len(set(self.goal_ids)):
            raise ValueError("Goal identifiers must be unique")
        return self


class GoalCriterionAssessmentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: GoalCriterionResult
    rationale: str = Field(min_length=1, max_length=5000)
    confidence: float = Field(ge=0, le=1)
    supporting_mapping_ids: list[str] = Field(default_factory=list, max_length=100)
    contradictory_mapping_ids: list[str] = Field(default_factory=list, max_length=100)
    completed_milestone_ids: list[str] = Field(default_factory=list, max_length=20)
    measured_value: float | None = None
    limitations: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_result(self):
        if self.result == GoalCriterionResult.NOT_ASSESSED:
            raise ValueError("NOT_ASSESSED is a backend state, not an AI assessment result")
        return self


class GoalAssessmentFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_type: GoalAssessmentFeedbackType
    corrected_result: GoalCriterionResult | None = None
    comment: Annotated[str | None, Field(max_length=4000)] = None

    @model_validator(mode="after")
    def validate_feedback(self):
        if self.feedback_type == GoalAssessmentFeedbackType.CORRECTED:
            if self.corrected_result in (None, GoalCriterionResult.NOT_ASSESSED):
                raise ValueError("Corrections must include an assessed result")
        elif self.corrected_result is not None:
            raise ValueError("Only corrected feedback may include a corrected result")
        if self.comment is not None and not self.comment.strip():
            raise ValueError("Feedback comments cannot be blank")
        return self
