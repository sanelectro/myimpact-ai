import copy
from datetime import UTC, datetime

import pytest

from app.evaluation.m66 import load_dataset
from app.evaluation.m66_eligibility import (
    MAXIMUM_THRESHOLD_METRICS,
    MINIMUM_THRESHOLD_METRICS,
    evaluate_release_eligibility,
)

APPROVAL_DATE = "2026-10-20T12:00:00Z"
EVALUATED_AT = datetime(2026, 10, 25, 12, tzinfo=UTC)


def check_eligibility(dataset, runs):
    return evaluate_release_eligibility(
        dataset,
        runs,
        evaluated_at=EVALUATED_AT,
    )


def make_approved_fixture():
    dataset = copy.deepcopy(load_dataset())
    evaluation_record = dataset["evaluation_record"]
    evaluation_record["approved_dataset_version"] = evaluation_record[
        "dataset_version"
    ]
    evaluation_record["approved_model_versions"] = ["fixture-model"]
    dataset["label_status"] = "HUMAN_REVIEWED"
    dataset["human_review"].update(
        {
            "status": "APPROVED",
            "reviewers": ["reviewer-one", "reviewer-two"],
            "approved_at": APPROVAL_DATE,
            "approved_dataset_version": evaluation_record["dataset_version"],
            "adjudication_status": "COMPLETED",
        }
    )
    dataset["threshold_approval"].update(
        {
            "status": "APPROVED",
            "approved_by": ["release-owner"],
            "approved_at": APPROVAL_DATE,
            "thresholds": {
                **{key: 0.0 for key in MINIMUM_THRESHOLD_METRICS},
                **{key: 1.0 for key in MAXIMUM_THRESHOLD_METRICS},
            },
        }
    )

    run_records = []
    for case in dataset["cases"]:
        labels = case["labels"]
        for repeat_index in range(1, evaluation_record["required_repeats"] + 1):
            run_records.append(
                {
                    "case_id": case["case_id"],
                    "repeat_index": repeat_index,
                    "status": "SUCCEEDED",
                    "dataset_version": evaluation_record["dataset_version"],
                    "prompt_version": evaluation_record["prompt_version"],
                    "model_version": "fixture-model",
                    "result": labels["expected_result"],
                    "rationale": labels["expected_rationale"],
                    "confidence": 0.8,
                    "supporting_mapping_ids": labels[
                        "expected_supporting_mapping_ids"
                    ],
                    "contradictory_mapping_ids": labels[
                        "expected_contradictory_mapping_ids"
                    ],
                    "completed_milestone_ids": [],
                    "measured_value": labels["expected_measured_value"],
                    "limitations": [],
                }
            )
    return dataset, run_records


def reason_codes(report):
    return {reason["code"] for reason in report["reasons"]}


def test_current_dataset_remains_ineligible_with_specific_reasons():
    dataset = load_dataset()

    report = check_eligibility(dataset, [])

    assert report["eligible"] is False
    assert {
        "dataset_labels_not_reviewed",
        "human_review_not_approved",
        "reviewer_identities_missing",
        "human_review_date_invalid",
        "adjudication_incomplete",
        "thresholds_not_approved",
        "threshold_approver_identities_missing",
        "threshold_approval_date_invalid",
        "approved_dataset_version_missing",
        "approved_model_versions_missing",
        "threshold_value_invalid_type",
        "run_missing",
    } <= reason_codes(report)
    assert dataset["label_status"] == "DRAFT_UNREVIEWED"
    assert dataset["human_review"]["status"] == "PENDING"
    assert dataset["threshold_approval"]["status"] == "NOT_APPROVED"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("reviewers", [], "reviewer_identities_missing"),
        ("reviewers", [" ", "reviewer-two"], "reviewer_identity_invalid"),
        ("reviewers", ["reviewer-one"], "reviewer_count_insufficient"),
        ("reviewers", ["Reviewer-One", " reviewer-one "], "reviewer_count_insufficient"),
        ("approved_by", [], "threshold_approver_identities_missing"),
        ("approved_by", ["  "], "threshold_approver_identity_invalid"),
    ],
)
def test_requires_valid_distinct_reviewers_and_approvers(
    field,
    value,
    expected_code,
):
    dataset, runs = make_approved_fixture()
    if field == "reviewers":
        dataset["human_review"][field] = value
    else:
        dataset["threshold_approval"][field] = value

    report = check_eligibility(dataset, runs)

    assert report["eligible"] is False
    assert expected_code in reason_codes(report)


@pytest.mark.parametrize(
    ("section", "value", "expected_code"),
    [
        ("human_review", None, "human_review_date_invalid"),
        ("human_review", "not-a-date", "human_review_date_invalid"),
        ("human_review", "2099-01-01T00:00:00Z", "human_review_date_invalid"),
        ("threshold_approval", None, "threshold_approval_date_invalid"),
        ("threshold_approval", "2026-10-20", "threshold_approval_date_invalid"),
    ],
)
def test_requires_valid_approval_dates(section, value, expected_code):
    dataset, runs = make_approved_fixture()
    dataset[section]["approved_at"] = value

    report = check_eligibility(dataset, runs)

    assert report["eligible"] is False
    assert expected_code in reason_codes(report)


@pytest.mark.parametrize(
    ("value", "expected_code"),
    [
        ("missing", "threshold_missing"),
        (True, "threshold_value_invalid_type"),
        ("0.5", "threshold_value_invalid_type"),
        (float("nan"), "threshold_value_invalid_type"),
        (float("inf"), "threshold_value_invalid_type"),
        (-0.01, "threshold_value_out_of_range"),
        (1.01, "threshold_value_out_of_range"),
        (10**1000, "threshold_value_out_of_range"),
    ],
)
def test_rejects_missing_or_invalid_threshold_values(value, expected_code):
    dataset, runs = make_approved_fixture()
    thresholds = dataset["threshold_approval"]["thresholds"]
    if value == "missing":
        thresholds.pop("citation_validity")
    else:
        thresholds["citation_validity"] = value

    report = check_eligibility(dataset, runs)

    assert report["eligible"] is False
    assert expected_code in reason_codes(report)


@pytest.mark.parametrize(
    ("mutate", "expected_codes"),
    [
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"approved_dataset_version": "older-version"}
            ),
            {"approved_dataset_version_mismatch"},
        ),
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"dataset_version": None}
            ),
            {"dataset_version_missing"},
        ),
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"prompt_version": None}
            ),
            {"prompt_version_missing"},
        ),
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"prompt_version": "old-prompt"}
            ),
            {"declared_prompt_version_mismatch", "run_prompt_version_mismatch"},
        ),
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"approved_model_versions": []}
            ),
            {"approved_model_versions_missing", "run_model_version_not_approved"},
        ),
        (
            lambda dataset, runs: runs[0].update({"dataset_version": "old-dataset"}),
            {"run_dataset_version_mismatch"},
        ),
        (
            lambda dataset, runs: runs[0].update({"prompt_version": "old-prompt"}),
            {"run_prompt_version_mismatch"},
        ),
        (
            lambda dataset, runs: runs[0].update({"model_version": "unapproved-model"}),
            {"run_model_version_not_approved"},
        ),
        (
            lambda dataset, runs: runs[0].update({"model_version": None}),
            {"run_model_version_missing"},
        ),
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"dataset_version": "different-version"}
            ),
            {"dataset_version_mismatch"},
        ),
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"approved_dataset_version": None}
            ),
            {"approved_dataset_version_missing"},
        ),
        (
            lambda dataset, runs: dataset["evaluation_record"].update(
                {"required_case_ids": dataset["evaluation_record"]["required_case_ids"][:-1]}
            ),
            {"unexpected_dataset_case"},
        ),
        (
            lambda dataset, runs: dataset["cases"].pop(),
            {"required_case_missing"},
        ),
    ],
)
def test_rejects_missing_or_mismatched_versions(mutate, expected_codes):
    dataset, runs = make_approved_fixture()
    mutate(dataset, runs)

    report = check_eligibility(dataset, runs)

    assert report["eligible"] is False
    assert expected_codes <= reason_codes(report)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda dataset, runs: runs.pop(),
            "run_missing",
        ),
        (
            lambda dataset, runs: runs.append(copy.deepcopy(runs[0])),
            "run_duplicate",
        ),
        (
            lambda dataset, runs: runs[0].update(
                {"status": "FAILED", "error_type": "OpenAIError"}
            ),
            "run_failed",
        ),
        (
            lambda dataset, runs: runs[0].update({"confidence": "not-numeric"}),
            "run_result_malformed",
        ),
        (
            lambda dataset, runs: runs[0].update(
                {"supporting_mapping_ids": ["unknown-mapping"]}
            ),
            "run_citations_invalid",
        ),
        (
            lambda dataset, runs: runs[0].update({"repeat_index": True}),
            "run_repeat_index_invalid",
        ),
    ],
)
def test_rejects_missing_duplicate_failed_and_malformed_runs(
    mutate,
    expected_code,
):
    dataset, runs = make_approved_fixture()
    mutate(dataset, runs)

    report = check_eligibility(dataset, runs)

    assert report["eligible"] is False
    assert expected_code in reason_codes(report)
    assert report["metrics"]["run_success_rate"] < 1.0


def test_malformed_dataset_case_is_ineligible_without_crashing():
    dataset, runs = make_approved_fixture()
    dataset["cases"][0]["labels"]["expected_supporting_mapping_ids"] = None

    report = check_eligibility(dataset, runs)

    assert report["eligible"] is False
    assert "dataset_case_reference_ids_malformed" in reason_codes(report)
    assert "dataset_case_achievement_uncited" in reason_codes(report)


def test_eligible_synthetic_approval_does_not_modify_real_dataset():
    real_dataset = load_dataset()
    synthetic_dataset, runs = make_approved_fixture()

    report = check_eligibility(synthetic_dataset, runs)

    assert report["eligible"] is True
    assert report["reasons"] == []
    assert report["metrics"]["run_success_rate"] == 1.0
    assert real_dataset["label_status"] == "DRAFT_UNREVIEWED"
    assert real_dataset["human_review"]["status"] == "PENDING"
    assert real_dataset["threshold_approval"]["status"] == "NOT_APPROVED"


def test_metrics_must_meet_approved_thresholds():
    dataset, runs = make_approved_fixture()
    dataset["threshold_approval"]["thresholds"]["evidence_matching_precision"] = 1.0
    runs[0]["supporting_mapping_ids"] = ["mapping-canary-irrelevant"]

    report = check_eligibility(dataset, runs)

    assert report["eligible"] is False
    assert "metric_below_threshold" in reason_codes(report)
    assert any(
        reason.get("metric") == "evidence_matching_precision"
        for reason in report["reasons"]
    )


def test_requested_repeat_count_must_match_the_evaluation_record():
    dataset, runs = make_approved_fixture()
    report = evaluate_release_eligibility(
        dataset,
        runs,
        evaluated_at=EVALUATED_AT,
        requested_repeats=dataset["evaluation_record"]["required_repeats"] - 1,
    )

    assert report["eligible"] is False
    assert "requested_repeat_count_mismatch" in reason_codes(report)


def test_evaluation_timestamp_must_be_timezone_aware():
    dataset, runs = make_approved_fixture()
    report = evaluate_release_eligibility(
        dataset,
        runs,
        evaluated_at=datetime(2026, 10, 25, 12),
    )

    assert report["eligible"] is False
    assert "evaluation_timestamp_invalid" in reason_codes(report)


def test_ineligibility_reasons_are_deterministic():
    dataset, runs = make_approved_fixture()
    runs.pop()
    runs.append(copy.deepcopy(runs[0]))
    runs[0]["prompt_version"] = "wrong-version"

    first_report = check_eligibility(dataset, runs)
    second_report = check_eligibility(dataset, list(reversed(runs)))

    assert first_report["reasons"] == second_report["reasons"]
