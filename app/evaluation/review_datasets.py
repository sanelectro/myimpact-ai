"""Dataset adapters for the shared human-review workflow."""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.assessment_evaluation import DATASET_PATHS, load_dataset_by_id
from app.evaluation.goal_validation_benchmark import (
    DATASET_PATH,
    DATASET_VERSION,
    load_dataset,
)
from app.models.goal_validation import GoalValidationDimension, GoalValidationStatus

REVIEW_DATASET_PATHS = {**DATASET_PATHS, "goal-validation": DATASET_PATH}
PROPOSAL_DATASET_ID = "goal-validation-v1"
PROPOSAL_DATASET_VERSION = "1.0.0"
PROPOSAL_SOURCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs" / "milestones" / "M6.6-goal-validation-v1-final.json"
)
REVIEW_DATASET_PATHS[PROPOSAL_DATASET_ID] = PROPOSAL_SOURCE_PATH


class ProposalSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_label: GoalValidationStatus
    rationale: str = Field(min_length=1)
    identified_findings: list[dict[str, Any]]
    missing_information: list[str]
    suggested_questions: list[str]
    suggested_improvements: list[str]
    model_reference: str | None
    prompt_version: str | None
    rubric_version: str = Field(min_length=1)
    evaluation_run_id: str | None
    generated_at: str | None
    suggestion_status: Literal["PROPOSED_NOT_HUMAN_APPROVED"]


class ProposalCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str = Field(min_length=1)
    case_version: int = Field(ge=1)
    case_name: str
    category: str = Field(min_length=1)
    goal: dict[str, Any]
    context: dict[str, Any]
    ai_suggestion: ProposalSuggestion
    human_review: dict[str, Any]
    reference: dict[str, Any]

    @model_validator(mode="after")
    def unreviewed_input(self):
        if self.goal.get("title") != self.case_name:
            raise ValueError(f"{self.case_id}: case name and goal title differ")
        if (
            self.human_review.get("review_status") != "NOT_STARTED"
            or self.human_review.get("reviews")
            or self.human_review.get("review_assignments")
            or self.human_review.get("resolution") is not None
            or self.reference.get("approval_status") != "NOT_APPROVED"
            or self.reference.get("reference_label") is not None
        ):
            raise ValueError(f"{self.case_id}: human reviews and references must be unapproved")
        return self


class ProposalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: dict[str, Any]
    evaluation_configuration: dict[str, Any]
    cases: list[ProposalCase] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_metadata(self):
        if (
            self.dataset.get("dataset_id") != PROPOSAL_DATASET_ID
            or self.dataset.get("dataset_version") != PROPOSAL_DATASET_VERSION
            or self.dataset.get("case_count") != len(self.cases)
            or self.dataset.get("review_status") != "DRAFT_UNREVIEWED"
            or self.dataset.get("ground_truth_status") != "NOT_APPROVED"
            or self.evaluation_configuration.get("review_mode") != "DUAL_ADJUDICATED"
            or self.evaluation_configuration.get("blind_human_review") is not True
        ):
            raise ValueError("Invalid or approved Goal Validation proposal dataset metadata")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Proposal case IDs must be unique")
        if any(
            case.ai_suggestion.rubric_version
            != self.evaluation_configuration.get("validation_rubric_version")
            for case in self.cases
        ):
            raise ValueError("Each proposal must use the declared rubric version")
        return self


def load_proposal_dataset(path: Path = PROPOSAL_SOURCE_PATH) -> ProposalDataset:
    return ProposalDataset.model_validate_json(path.read_text(encoding="utf-8"))


def load_review_dataset_by_id(dataset_id: str, dataset_version: str) -> dict:
    if dataset_id == PROPOSAL_DATASET_ID:
        if dataset_version != PROPOSAL_DATASET_VERSION:
            raise FileNotFoundError(f"Unknown goal-validation dataset version: {dataset_version}")
        source = load_proposal_dataset()
        source_data = json.loads(PROPOSAL_SOURCE_PATH.read_text(encoding="utf-8"))
        source_hash = hashlib.sha256(
            json.dumps(source_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "dataset_id": dataset_id,
            "label_status": "DRAFT_UNREVIEWED",
            "evaluation_record": {
                "dataset_version": dataset_version,
                "categories": sorted({case.category for case in source.cases}),
                "benchmark_dimensions": [dimension.value for dimension in GoalValidationDimension],
                "source_content_hash": source_hash,
                "source_dataset_id": source.dataset["dataset_id"],
                "rubric_version": source.evaluation_configuration["validation_rubric_version"],
                "review_kind": "GOAL_VALIDATION",
            },
            "cases": [
                {
                    "case_id": case.case_id,
                    "case_version": case.case_version,
                    "category": case.category,
                    "review_kind": "GOAL_VALIDATION",
                    "scenario": (
                        "Assess goal readiness independently. Include dimensions, missing "
                        "information, and clarification questions in your rationale."
                    ),
                    "goal": case.goal,
                    "goal_validation_context": case.context,
                    "review_label_options": [status.value for status in GoalValidationStatus],
                    "benchmark_dimensions": [dimension.value for dimension in GoalValidationDimension],
                    "label_status": "DRAFT_UNREVIEWED",
                    "reference_visibility": "BLIND",
                }
                for case in source.cases
            ],
        }
    if dataset_id != "goal-validation":
        return load_dataset_by_id(dataset_id, dataset_version)
    if dataset_version != DATASET_VERSION:
        raise FileNotFoundError(f"Unknown goal-validation dataset version: {dataset_version}")
    dataset = load_dataset().model_dump(mode="json")
    source_hash = hashlib.sha256(
        json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    dimensions = [dimension.value for dimension in GoalValidationDimension]
    return {
        "dataset_id": dataset_id,
        "label_status": dataset["label_status"],
        "evaluation_record": {
            "dataset_version": dataset_version,
            "categories": sorted({case["category"] for case in dataset["cases"]}),
            "benchmark_dimensions": dimensions,
            "source_content_hash": source_hash,
            "review_kind": "GOAL_VALIDATION",
        },
        "cases": [
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "review_kind": "GOAL_VALIDATION",
                "scenario": (
                    "Assess this goal's readiness, not employee achievement or evidence. "
                    "Record the readiness status and explain missing information, "
                    "dimension findings, and clarification questions in your rationale."
                ),
                "goal": case["input"]["goal"],
                "goal_validation_context": case["input"]["context"],
                "review_label_options": [status.value for status in GoalValidationStatus],
                "benchmark_dimensions": dimensions,
                "label_status": case["label_status"],
                "reference_visibility": "BLIND",
            }
            for case in dataset["cases"]
        ],
    }
