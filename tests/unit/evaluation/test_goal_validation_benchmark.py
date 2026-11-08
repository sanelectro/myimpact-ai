import copy

import pytest
from pydantic import ValidationError

from app.evaluation.goal_validation_benchmark import (
    CATEGORIES,
    BenchmarkDataset,
    evaluate_benchmark,
    load_dataset,
)


def _prediction(case):
    reference = case.provisional_reference
    return {
        "dimensions": reference.expected_dimensions,
        "findings": [
            {
                "dimension": reference.expected_dimensions[0],
                "finding_code": finding,
            }
            for finding in reference.expected_findings
        ],
        "questions": reference.expected_questions,
        "improvement": reference.expected_improvement,
        "missing_information": reference.expected_missing_information,
        "status": reference.expected_status,
        "accountability": case.input["goal"]["accountability"],
    }


def test_starter_dataset_has_30_draft_cases_with_five_per_category():
    dataset = load_dataset()

    assert len(dataset.cases) == 30
    assert {case.category for case in dataset.cases} == CATEGORIES
    assert {case.category: sum(c.category == case.category for c in dataset.cases)
            for case in dataset.cases} == {category: 5 for category in CATEGORIES}
    assert dataset.label_status == "DRAFT_UNREVIEWED"
    assert dataset.human_review["status"] == "PENDING"
    assert dataset.threshold_approval.status == "NOT_APPROVED"
    assert all(value is None for value in dataset.threshold_approval.thresholds.values())
    assert all(case.label_status == "DRAFT_UNREVIEWED" for case in dataset.cases)
    assert all(case.human_review.status == "PENDING" for case in dataset.cases)
    assert all(case.adjudicated_reference is None for case in dataset.cases)
    assert all(
        {"expected_dimensions", "expected_findings", "expected_questions",
         "expected_improvement", "expected_status", "reference_rationale"}
        <= set(case.provisional_reference.model_fields_set)
        for case in dataset.cases
    )


def test_loader_rejects_duplicate_ids_and_unreviewed_dataset_with_approved_thresholds():
    dataset_dict = load_dataset().model_dump(mode="json")
    duplicate = copy.deepcopy(dataset_dict)
    duplicate["cases"][1]["case_id"] = duplicate["cases"][0]["case_id"]
    with pytest.raises(ValidationError, match="case_id values must be unique"):
        BenchmarkDataset.model_validate(duplicate)

    accidentally_approved = copy.deepcopy(dataset_dict)
    accidentally_approved["threshold_approval"]["status"] = "APPROVED"
    with pytest.raises(ValidationError, match="must not approve thresholds"):
        BenchmarkDataset.model_validate(accidentally_approved)


def test_metric_outputs_cover_classification_status_and_accountability():
    dataset = load_dataset()
    case = dataset.cases[0]
    report = evaluate_benchmark(
        dataset,
        [{"case_id": case.case_id, "repeat_index": 1, "prediction": _prediction(case)}],
    )
    metrics = report["metrics"]

    assert metrics["dimension_classification"]["f1"] == 1.0
    assert metrics["finding_classification"]["precision"] == 1.0
    assert metrics["finding_classification"]["recall"] == 1.0
    assert metrics["missing_information_recall"] == 1.0
    assert metrics["readiness_status"]["accuracy"] == 1.0
    assert metrics["readiness_status"]["ready_false_positive_rate"] == 0.0
    assert metrics["readiness_status"]["ready_false_negative_rate"] == 0.0
    assert metrics["accountability_preservation_rate"] == 1.0
    assert metrics["structured_output_validity"] == 1.0
    assert metrics["repeatability"]["score"] is None


def test_repeatability_is_reported_for_multiple_runs_and_malformed_output_is_invalid():
    dataset = load_dataset()
    case = dataset.cases[0]
    prediction = _prediction(case)
    report = evaluate_benchmark(
        dataset,
        [
            {"case_id": case.case_id, "repeat_index": 1, "prediction": prediction},
            {"case_id": case.case_id, "repeat_index": 2, "prediction": prediction},
            {"case_id": "gv-02", "repeat_index": 1, "prediction": {"status": "READY"}},
        ],
    )

    assert report["metrics"]["repeatability"]["score"] == 1.0
    assert report["metrics"]["repeatability"]["cases_with_multiple_runs"] == 1
    assert report["metrics"]["structured_output_validity"] == pytest.approx(2 / 3)
    assert report["metrics"]["invalid_outputs"] == 1
    assert report["output_errors"][0]["error"] == "invalid_structured_output"


def test_legacy_and_renamed_statuses_are_equivalent_in_metrics():
    dataset = load_dataset()
    case = next(
        case for case in dataset.cases
        if case.provisional_reference.expected_status == "NEEDS_IMPROVEMENT"
    )
    old_prediction = _prediction(case)
    new_prediction = {**old_prediction, "status": "NEEDS_REFINEMENT"}
    report = evaluate_benchmark(dataset, [
        {"case_id": case.case_id, "repeat_index": 1, "prediction": old_prediction},
        {"case_id": case.case_id, "repeat_index": 2, "prediction": new_prediction},
    ])
    assert report["metrics"]["readiness_status"]["accuracy"] == 1.0
    assert report["metrics"]["repeatability"]["score"] == 1.0


def test_unreviewed_starter_never_becomes_release_evidence():
    dataset = load_dataset()
    report = evaluate_benchmark(dataset, [])

    assert report["evidence_class"] == "NON_RELEASE_EXPLORATORY"
    assert report["release_eligibility"]["eligible"] is False
    assert "dataset_labels_not_human_reviewed" in report["release_eligibility"]["reasons"]
    assert "dataset_human_review_not_approved" in report["release_eligibility"]["reasons"]
    assert "case_not_reviewed:gv-01" in report["release_eligibility"]["reasons"]
    assert "case_not_adjudicated:gv-01" in report["release_eligibility"]["reasons"]
    assert "thresholds_not_explicitly_approved" in report["release_eligibility"]["reasons"]
