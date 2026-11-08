"""Independent, draft-only benchmark tooling for goal validation."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models.goal_validation import GoalValidationStatus

DATASET_VERSION = "goal-validation-v1"
DATASET_PATH = (
    Path(__file__).resolve().parents[2] / "evaluation" / "goal_validation_v1.json"
)
CATEGORIES = {
    "clarity_structure",
    "ownership_accountability",
    "delivery_outcome_impact",
    "smart_measurability",
    "feasibility_role_alignment",
    "conflicting_incomplete",
}
DIMENSIONS = {
    "structure",
    "accountability",
    "success_criteria",
    "deliverables",
    "measurement",
    "timeframe",
}
FINDINGS = {
    "missing_title",
    "missing_accountability",
    "missing_success_criteria",
    "missing_deliverables",
    "inconsistent_timeframe",
    "incomplete_measurement_context",
    "ambiguous_intent",
    "ambiguous_accountability",
    "ambiguous_success_criteria",
    "conflicting_details",
    "ambiguous_timeframe",
}
STATUSES = {
    "READY", "NEEDS_IMPROVEMENT", "NEEDS_REVIEW", "NEEDS_REFINEMENT",
    "NEEDS_DISCUSSION", "INVALID",
}
THRESHOLD_METRICS = {
    "dimension_f1",
    "finding_precision",
    "finding_recall",
    "missing_information_recall",
    "status_accuracy",
    "ready_false_positive_rate",
    "ready_false_negative_rate",
    "accountability_preservation_rate",
    "structured_output_validity",
    "repeatability",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalInput(StrictModel):
    title: str | None = None
    description: str | None = None
    goal_type: str | None = None
    accountability: str | None = None
    scope: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    outcome: str | None = None
    impact: str | None = None
    measurement: str | None = None
    baseline: str | None = None
    target: str | None = None
    timeframe: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    role_alignment: str | None = None


class CaseReview(StrictModel):
    status: Literal["PENDING", "IN_REVIEW", "APPROVED", "REJECTED"] = "PENDING"
    reviewer_slots: list[dict[str, Any]] = Field(default_factory=list)
    adjudication_status: Literal["PENDING", "ADJUDICATED", "NOT_REQUIRED"] = "PENDING"
    adjudicated_by: str | None = None
    adjudicated_at: str | None = None
    notes: str | None = None


class ReferenceLabels(StrictModel):
    expected_dimensions: list[str]
    expected_findings: list[str]
    expected_questions: list[str]
    expected_improvement: str | None
    expected_missing_information: list[str]
    expected_status: str
    reference_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_label_vocabulary(self) -> ReferenceLabels:
        if not set(self.expected_dimensions) <= DIMENSIONS:
            raise ValueError("Reference contains an unsupported dimension")
        if not set(self.expected_findings) <= FINDINGS:
            raise ValueError("Reference contains an unsupported finding")
        if self.expected_status not in STATUSES:
            raise ValueError("Reference contains an unsupported status")
        if len(set(self.expected_dimensions)) != len(self.expected_dimensions):
            raise ValueError("Reference dimensions must be unique")
        if len(set(self.expected_findings)) != len(self.expected_findings):
            raise ValueError("Reference findings must be unique")
        return self


class BenchmarkCase(StrictModel):
    case_id: str = Field(min_length=1)
    category: str
    label_status: Literal["DRAFT_UNREVIEWED", "HUMAN_REVIEWED"]
    input: dict[str, Any]
    provisional_reference: ReferenceLabels
    adjudicated_reference: ReferenceLabels | None = None
    human_review: CaseReview

    @model_validator(mode="after")
    def validate_category_and_input(self) -> BenchmarkCase:
        if self.category not in CATEGORIES:
            raise ValueError(f"Unknown category: {self.category}")
        if set(self.input) != {"goal", "context"}:
            raise ValueError("Case input must contain goal and context only")
        GoalInput.model_validate(self.input["goal"])
        if not isinstance(self.input["context"], dict):
            raise TypeError("Case context must be an object")
        return self


class ThresholdApproval(StrictModel):
    status: Literal["NOT_APPROVED", "APPROVED"] = "NOT_APPROVED"
    approved_by: str | None = None
    approved_at: str | None = None
    thresholds: dict[str, float | None]


class BenchmarkDataset(StrictModel):
    dataset_id: Literal["goal-validation"]
    dataset_version: Literal["goal-validation-v1"]
    label_status: Literal["DRAFT_UNREVIEWED", "HUMAN_REVIEWED"]
    dataset_status: Literal["DRAFT_UNREVIEWED", "HUMAN_REVIEWED"]
    human_review: dict[str, Any]
    threshold_approval: ThresholdApproval
    cases: list[BenchmarkCase]

    @model_validator(mode="after")
    def validate_draft_and_coverage(self) -> BenchmarkDataset:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique")
        if len(self.cases) != 30:
            raise ValueError("goal-validation-v1 must contain exactly 30 cases")
        counts = Counter(case.category for case in self.cases)
        if set(counts) != CATEGORIES or any(counts[key] != 5 for key in CATEGORIES):
            raise ValueError("Each of the six categories must contain five cases")
        if self.label_status == "DRAFT_UNREVIEWED":
            if self.dataset_status != "DRAFT_UNREVIEWED":
                raise ValueError("Draft labels require a draft dataset status")
            if self.human_review.get("status") != "PENDING":
                raise ValueError("Draft dataset must remain pending human review")
            if self.threshold_approval.status != "NOT_APPROVED":
                raise ValueError("Draft dataset must not approve thresholds")
            if any(
                value is not None
                for value in self.threshold_approval.thresholds.values()
            ):
                raise ValueError("Draft dataset thresholds must be unset")
            if any(
                case.label_status != "DRAFT_UNREVIEWED"
                or case.human_review.status != "PENDING"
                or case.adjudicated_reference is not None
                for case in self.cases
            ):
                raise ValueError("Every draft case must remain unreviewed")
        return self


class PredictedFinding(StrictModel):
    dimension: str
    finding_code: str

    @model_validator(mode="after")
    def validate_vocabulary(self) -> PredictedFinding:
        if self.dimension not in DIMENSIONS:
            raise ValueError("Finding contains an unsupported dimension")
        if self.finding_code not in FINDINGS:
            raise ValueError("Finding contains an unsupported finding code")
        return self


class GoalValidationPrediction(StrictModel):
    dimensions: list[str]
    findings: list[PredictedFinding]
    questions: list[str]
    improvement: str | None
    missing_information: list[str]
    status: str
    accountability: str | None

    @model_validator(mode="after")
    def validate_vocabulary(self) -> GoalValidationPrediction:
        if not set(self.dimensions) <= DIMENSIONS:
            raise ValueError("Prediction contains an unsupported dimension")
        if self.status not in STATUSES:
            raise ValueError("Prediction contains an unsupported status")
        self.status = GoalValidationStatus(self.status).value
        if any(finding.dimension not in DIMENSIONS for finding in self.findings):
            raise ValueError("Finding contains an unsupported dimension")
        return self


def load_dataset(path: Path = DATASET_PATH) -> BenchmarkDataset:
    """Load and fully validate the standalone goal-validation dataset."""
    with path.open(encoding="utf-8") as dataset_file:
        return BenchmarkDataset.model_validate_json(dataset_file.read())


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _prediction_metrics(
    dataset: BenchmarkDataset,
    prediction_records: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_id = {case.case_id: case for case in dataset.cases}
    valid: list[tuple[BenchmarkCase, GoalValidationPrediction, int]] = []
    invalid_count = 0
    seen: set[tuple[str, int]] = set()
    errors: list[dict[str, Any]] = []
    for record in prediction_records:
        if not isinstance(record, dict):
            invalid_count += 1
            errors.append({"error": "record_must_be_object"})
            continue
        case_id = record.get("case_id")
        repeat_index = record.get("repeat_index", 1)
        if case_id not in by_id or not isinstance(repeat_index, int) or isinstance(repeat_index, bool) or repeat_index < 1:
            invalid_count += 1
            errors.append({"case_id": case_id, "error": "invalid_case_or_repeat_index"})
            continue
        key = (case_id, repeat_index)
        if key in seen:
            invalid_count += 1
            errors.append({"case_id": case_id, "repeat_index": repeat_index, "error": "duplicate_run"})
            continue
        seen.add(key)
        try:
            prediction = GoalValidationPrediction.model_validate(record.get("prediction"))
        except ValidationError as exc:
            invalid_count += 1
            errors.append(
                {
                    "case_id": case_id,
                    "repeat_index": repeat_index,
                    "error": "invalid_structured_output",
                    "details": exc.errors(include_url=False),
                }
            )
            continue
        valid.append((by_id[case_id], prediction, repeat_index))

    dimension_tp = dimension_fp = dimension_fn = 0
    finding_tp = finding_fp = finding_fn = 0
    missing_tp = missing_fn = 0
    status_correct = ready_fp = ready_fn = 0
    accountability_correct = 0
    predictions_by_case: dict[str, list[GoalValidationPrediction]] = defaultdict(list)

    for case, prediction, _ in valid:
        reference = case.adjudicated_reference or case.provisional_reference
        expected_dimensions = set(reference.expected_dimensions)
        predicted_dimensions = set(prediction.dimensions)
        dimension_tp += len(expected_dimensions & predicted_dimensions)
        dimension_fp += len(predicted_dimensions - expected_dimensions)
        dimension_fn += len(expected_dimensions - predicted_dimensions)

        expected_findings = set(reference.expected_findings)
        predicted_findings = {finding.finding_code for finding in prediction.findings}
        finding_tp += len(expected_findings & predicted_findings)
        finding_fp += len(predicted_findings - expected_findings)
        finding_fn += len(expected_findings - predicted_findings)

        expected_missing = set(reference.expected_missing_information)
        predicted_missing = set(prediction.missing_information)
        missing_tp += len(expected_missing & predicted_missing)
        missing_fn += len(expected_missing - predicted_missing)

        status_correct += (
            GoalValidationStatus(prediction.status)
            == GoalValidationStatus(reference.expected_status)
        )
        was_ready = reference.expected_status == "READY"
        predicted_ready = prediction.status == "READY"
        ready_fp += int(not was_ready and predicted_ready)
        ready_fn += int(was_ready and not predicted_ready)
        accountability_correct += (
            prediction.accountability == case.input["goal"].get("accountability")
        )
        predictions_by_case[case.case_id].append(prediction)

    dimension_precision = _ratio(dimension_tp, dimension_tp + dimension_fp)
    dimension_recall = _ratio(dimension_tp, dimension_tp + dimension_fn)
    finding_precision = _ratio(finding_tp, finding_tp + finding_fp)
    finding_recall = _ratio(finding_tp, finding_tp + finding_fn)
    comparison_count = len(valid)
    repeatable_cases = [
        predictions
        for predictions in predictions_by_case.values()
        if len(predictions) > 1
    ]
    repeatability = None
    if repeatable_cases:
        repeatability = _ratio(
            sum(
                len(
                    {
                        json.dumps(
                            prediction.model_dump(mode="json"),
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        for prediction in predictions
                    }
                )
                == 1
                for predictions in repeatable_cases
            ),
            len(repeatable_cases),
        )

    metrics = {
        "dimension_classification": {
            "precision": dimension_precision,
            "recall": dimension_recall,
            "f1": _f1(dimension_precision, dimension_recall),
            "true_positive": dimension_tp,
            "false_positive": dimension_fp,
            "false_negative": dimension_fn,
        },
        "finding_classification": {
            "precision": finding_precision,
            "recall": finding_recall,
            "f1": _f1(finding_precision, finding_recall),
            "true_positive": finding_tp,
            "false_positive": finding_fp,
            "false_negative": finding_fn,
        },
        "missing_information_recall": _ratio(missing_tp, missing_tp + missing_fn),
        "readiness_status": {
            "accuracy": _ratio(status_correct, comparison_count),
            "ready_false_positive_rate": _ratio(ready_fp, sum(
                case.provisional_reference.expected_status != "READY"
                for case, _, _ in valid
            )),
            "ready_false_negative_rate": _ratio(ready_fn, sum(
                case.provisional_reference.expected_status == "READY"
                for case, _, _ in valid
            )),
            "correct": status_correct,
            "evaluated": comparison_count,
            "ready_false_positive": ready_fp,
            "ready_false_negative": ready_fn,
        },
        "accountability_preservation_rate": _ratio(
            accountability_correct, comparison_count
        ),
        "structured_output_validity": _ratio(
            comparison_count, comparison_count + invalid_count
        ),
        "repeatability": {
            "score": repeatability,
            "cases_with_multiple_runs": len(repeatable_cases),
            "repeat_count_by_case": {
                case_id: len(predictions)
                for case_id, predictions in sorted(predictions_by_case.items())
                if len(predictions) > 1
            },
        },
        "valid_outputs": comparison_count,
        "invalid_outputs": invalid_count,
    }
    return metrics, errors


def _release_eligibility(
    dataset: BenchmarkDataset, metrics: dict[str, Any]
) -> dict[str, Any]:
    reasons: list[str] = []
    if dataset.label_status != "HUMAN_REVIEWED":
        reasons.append("dataset_labels_not_human_reviewed")
    if dataset.dataset_status != "HUMAN_REVIEWED":
        reasons.append("dataset_status_not_approved")
    if dataset.human_review.get("status") != "APPROVED":
        reasons.append("dataset_human_review_not_approved")
    for case in dataset.cases:
        if (
            case.label_status != "HUMAN_REVIEWED"
            or case.human_review.status != "APPROVED"
        ):
            reasons.append(f"case_not_reviewed:{case.case_id}")
        if (
            case.human_review.adjudication_status != "ADJUDICATED"
            or not case.human_review.adjudicated_by
            or not case.human_review.adjudicated_at
            or case.adjudicated_reference is None
        ):
            reasons.append(f"case_not_adjudicated:{case.case_id}")
    approval = dataset.threshold_approval
    if approval.status != "APPROVED" or not approval.approved_by or not approval.approved_at:
        reasons.append("thresholds_not_explicitly_approved")
    threshold_values = approval.thresholds
    missing_thresholds = THRESHOLD_METRICS - set(threshold_values)
    if missing_thresholds:
        reasons.append("required_thresholds_missing")
    for key in THRESHOLD_METRICS & set(threshold_values):
        threshold = threshold_values[key]
        if threshold is None or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            reasons.append(f"threshold_unset_or_invalid:{key}")
            continue
        actual = {
            "dimension_f1": metrics["dimension_classification"]["f1"],
            "finding_precision": metrics["finding_classification"]["precision"],
            "finding_recall": metrics["finding_classification"]["recall"],
            "missing_information_recall": metrics["missing_information_recall"],
            "status_accuracy": metrics["readiness_status"]["accuracy"],
            "ready_false_positive_rate": metrics["readiness_status"]["ready_false_positive_rate"],
            "ready_false_negative_rate": metrics["readiness_status"]["ready_false_negative_rate"],
            "accountability_preservation_rate": metrics["accountability_preservation_rate"],
            "structured_output_validity": metrics["structured_output_validity"],
            "repeatability": metrics["repeatability"]["score"],
        }[key]
        if actual is None or (
            actual > threshold
            if key in {"ready_false_positive_rate", "ready_false_negative_rate"}
            else actual < threshold
        ):
            reasons.append(f"threshold_not_met:{key}")
    return {"eligible": not reasons, "reasons": reasons}


def evaluate_benchmark(
    dataset: BenchmarkDataset, prediction_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Score supplied outputs and always report draft data as exploratory evidence."""
    metrics, errors = _prediction_metrics(dataset, prediction_records)
    eligibility = _release_eligibility(dataset, metrics)
    return {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "dataset_label_status": dataset.label_status,
        "dataset_status": dataset.dataset_status,
        "human_review_status": dataset.human_review.get("status"),
        "threshold_approval_status": dataset.threshold_approval.status,
        "evidence_class": (
            "RELEASE_EVIDENCE" if eligibility["eligible"] else "NON_RELEASE_EXPLORATORY"
        ),
        "release_eligibility": eligibility,
        "metrics": metrics,
        "output_errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--predictions", type=Path, required=True)
    args = parser.parse_args()
    dataset = load_dataset(args.dataset)
    with args.predictions.open(encoding="utf-8") as predictions_file:
        predictions = json.load(predictions_file)
    if not isinstance(predictions, list):
        parser.error("prediction file must contain a JSON array")
    print(json.dumps(evaluate_benchmark(dataset, predictions), indent=2))


if __name__ == "__main__":
    main()
