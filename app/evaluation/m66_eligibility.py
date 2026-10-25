import math
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.exceptions import GoalCriterionAssessmentError
from app.models.goal_criteria import (
    GoalCriterionAssessmentProposal,
    GoalCriterionDefinition,
    GoalCriterionResult,
)
from app.services.goal_assessment import (
    ASSESSMENT_PROMPT_VERSION,
    GoalAssessmentService,
    validate_achievement_citation,
    validate_assessment_citations,
)

MINIMUM_THRESHOLD_METRICS = {
    "evidence_matching_precision": "evidence_matching_precision",
    "evidence_matching_recall": "evidence_matching_recall",
    "citation_validity": "citation_validity",
    "assessment_agreement": "assessment_agreement",
    "insufficient_evidence_abstention_accuracy": (
        "insufficient_evidence_abstention_accuracy"
    ),
    "repeatability": "repeatability",
    "run_success_rate": "run_success_rate",
}
MAXIMUM_THRESHOLD_METRICS = {
    "unsupported_assessment_claim_rate_max": (
        "unsupported_assessment_claim_rate"
    )
}
REQUIRED_THRESHOLDS = set(MINIMUM_THRESHOLD_METRICS) | set(
    MAXIMUM_THRESHOLD_METRICS
)
ACHIEVEMENT_RESULTS = {
    GoalCriterionResult.IN_PROGRESS,
    GoalCriterionResult.MET,
}
APPROVED_ADJUDICATION_STATUSES = {"COMPLETED", "NO_DISAGREEMENT"}


def calculate_metrics(
    cases: list[dict[str, Any]],
    run_records: list[dict[str, Any]],
    expected_repeats: int,
) -> dict[str, float | None]:
    runs_by_slot: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for run in run_records if isinstance(run_records, list) else []:
        if not isinstance(run, dict):
            continue
        case_id = run.get("case_id")
        repeat_index = run.get("repeat_index")
        if (
            isinstance(case_id, str)
            and isinstance(repeat_index, int)
            and not isinstance(repeat_index, bool)
        ):
            runs_by_slot[(case_id, repeat_index)].append(run)

    expected_evidence_count = 0
    predicted_evidence_count = 0
    matching_evidence_count = 0
    citation_count = 0
    matching_citation_count = 0
    agreement_count = 0
    abstention_count = 0
    correct_abstention_count = 0
    achievement_prediction_count = 0
    unsupported_assessment_claim_count = 0
    successful_slots = 0
    repeatable_cases = 0
    expected_slot_count = len(cases) * expected_repeats

    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        labels = case.get("labels", {})
        if not isinstance(labels, dict):
            labels = {}
        evidence_items = case.get("evidence", [])
        if not isinstance(evidence_items, list):
            evidence_items = []
        relevant_evidence = {
            ("SUPPORTING", mapping_id)
            for mapping_id in _string_list(
                labels.get("relevant_supporting_mapping_ids")
            )
        } | {
            ("CONTRADICTORY", mapping_id)
            for mapping_id in _string_list(
                labels.get("relevant_contradictory_mapping_ids")
            )
        }
        expected_evidence_count += (
            len(relevant_evidence) * expected_repeats
        )
        available_ids = {
            item.get("mapping_id")
            for item in evidence_items
            if isinstance(item, dict) and isinstance(item.get("mapping_id"), str)
        }
        signatures = []
        all_runs_valid = True

        for repeat_index in range(1, expected_repeats + 1):
            slot_records = runs_by_slot.get((case_id, repeat_index), [])
            if len(slot_records) != 1:
                all_runs_valid = False
                if not case.get("assessment_sufficient", False):
                    abstention_count += 1
                continue

            run = slot_records[0]
            validated = _validated_run_output(case, run)
            if run.get("status") != "SUCCEEDED" or validated is None:
                all_runs_valid = False
                if not case.get("assessment_sufficient", False):
                    abstention_count += 1
                continue

            proposal, assessed_result = validated
            successful_slots += 1
            agreement_count += assessed_result.value == labels.get(
                "expected_result"
            )
            support_ids = proposal.supporting_mapping_ids
            contradictory_ids = proposal.contradictory_mapping_ids
            actual_evidence = [
                ("SUPPORTING", mapping_id) for mapping_id in support_ids
            ] + [
                ("CONTRADICTORY", mapping_id)
                for mapping_id in contradictory_ids
            ]
            predicted_evidence_count += len(actual_evidence)
            matching_evidence_count += sum(
                item in relevant_evidence for item in actual_evidence
            )
            citations = support_ids + contradictory_ids
            citation_count += len(citations)
            matching_citation_count += sum(
                mapping_id in available_ids for mapping_id in citations
            )
            if not case.get("assessment_sufficient", False):
                abstention_count += 1
                correct_abstention_count += (
                    assessed_result == GoalCriterionResult.NEEDS_REVIEW
                )
            if assessed_result in ACHIEVEMENT_RESULTS:
                achievement_prediction_count += 1
                expected_achievement = (
                    labels.get("expected_result")
                    in {item.value for item in ACHIEVEMENT_RESULTS}
                )
                expected_support_ids = set(
                    _string_list(labels.get("relevant_supporting_mapping_ids"))
                )
                if (
                    not expected_achievement
                    or not expected_support_ids
                    or not set(support_ids).intersection(expected_support_ids)
                ):
                    unsupported_assessment_claim_count += 1
            signatures.append(
                (
                    assessed_result.value,
                    tuple(sorted(support_ids)),
                    tuple(sorted(contradictory_ids)),
                )
            )

        if (
            all_runs_valid
            and len(signatures) == expected_repeats
            and len(set(signatures)) == 1
        ):
            repeatable_cases += 1

    return {
        "evidence_matching_precision": _ratio(
            matching_evidence_count, predicted_evidence_count
        ),
        "evidence_matching_recall": _ratio(
            matching_evidence_count, expected_evidence_count
        ),
        "citation_validity": _ratio(matching_citation_count, citation_count),
        "unsupported_assessment_claim_rate": _ratio(
            unsupported_assessment_claim_count,
            achievement_prediction_count,
        ),
        "assessment_agreement": _ratio(agreement_count, expected_slot_count),
        "insufficient_evidence_abstention_accuracy": _ratio(
            correct_abstention_count, abstention_count
        ),
        "repeatability": _ratio(repeatable_cases, len(cases)),
        "run_success_rate": _ratio(successful_slots, expected_slot_count),
    }


def evaluate_release_eligibility(
    dataset: dict[str, Any],
    run_records: list[dict[str, Any]],
    *,
    evaluated_at: datetime,
    requested_repeats: int | None = None,
) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    if (
        not isinstance(evaluated_at, datetime)
        or evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() is None
    ):
        _add_reason(
            reasons,
            "evaluation_timestamp_invalid",
            "Evaluation timestamp must be timezone-aware.",
        )
        evaluation_reference = datetime.min.replace(tzinfo=UTC)
    else:
        evaluation_reference = evaluated_at
    if not isinstance(dataset, dict):
        _add_reason(reasons, "dataset_malformed", "Dataset is not an object.")
        return {"eligible": False, "reasons": reasons, "metrics": {}}
    evaluation_record = dataset.get("evaluation_record")
    human_review = dataset.get("human_review")
    threshold_approval = dataset.get("threshold_approval")
    cases = dataset.get("cases", [])
    if not isinstance(evaluation_record, dict):
        evaluation_record = {}
        _add_reason(reasons, "evaluation_record_missing", "Evaluation record is missing.")
    if not isinstance(human_review, dict):
        human_review = {}
        _add_reason(
            reasons,
            "human_review_metadata_missing",
            "Human-review metadata is missing.",
        )
    if not isinstance(threshold_approval, dict):
        threshold_approval = {}
        _add_reason(
            reasons,
            "threshold_approval_metadata_missing",
            "Threshold-approval metadata is missing.",
        )
    if not isinstance(cases, list) or not cases:
        cases = []
        _add_reason(reasons, "dataset_cases_missing", "Dataset has no evaluation cases.")

    dataset_id = _nonempty_string(dataset.get("dataset_id"))
    if dataset_id is None:
        _add_reason(reasons, "dataset_id_missing", "Dataset identifier is missing.")

    dataset_version = _nonempty_string(evaluation_record.get("dataset_version"))
    if dataset_version is None:
        _add_reason(
            reasons,
            "dataset_version_missing",
            "Evaluation record does not declare a dataset version.",
        )
    elif dataset_id is not None and dataset_version != dataset_id:
        _add_reason(
            reasons,
            "dataset_version_mismatch",
            "Declared dataset version does not match the dataset identifier.",
        )
    approved_dataset_version = _nonempty_string(
        evaluation_record.get("approved_dataset_version")
    )
    if approved_dataset_version is None:
        _add_reason(
            reasons,
            "approved_dataset_version_missing",
            "No dataset version has been approved.",
        )
    elif dataset_version is not None and approved_dataset_version != dataset_version:
        _add_reason(
            reasons,
            "approved_dataset_version_mismatch",
            "Approved dataset version does not match the evaluated dataset version.",
        )

    prompt_version = _nonempty_string(evaluation_record.get("prompt_version"))
    if prompt_version is None:
        _add_reason(
            reasons,
            "prompt_version_missing",
            "Evaluation record does not declare a prompt version.",
        )
    elif prompt_version != ASSESSMENT_PROMPT_VERSION:
        _add_reason(
            reasons,
            "declared_prompt_version_mismatch",
            "Declared prompt version does not match the current assessment prompt.",
        )

    approved_models = _identity_list(
        evaluation_record.get("approved_model_versions")
    )
    if not approved_models:
        _add_reason(
            reasons,
            "approved_model_versions_missing",
            "No approved model versions are declared.",
        )

    required_repeats = evaluation_record.get("required_repeats")
    repeats_valid = (
        isinstance(required_repeats, int)
        and not isinstance(required_repeats, bool)
        and required_repeats >= 1
    )
    if not repeats_valid:
        _add_reason(
            reasons,
            "required_repeats_invalid",
            "Required repeat count must be a positive integer.",
        )
        required_repeats = 0
    if requested_repeats is not None:
        if (
            not isinstance(requested_repeats, int)
            or isinstance(requested_repeats, bool)
            or requested_repeats < 1
        ):
            _add_reason(
                reasons,
                "requested_repeat_count_invalid",
                "Requested repeat count must be a positive integer.",
            )
        elif requested_repeats != required_repeats:
            _add_reason(
                reasons,
                "requested_repeat_count_mismatch",
                "Requested run count does not match the evaluation record.",
            )

    _validate_human_review(
        reasons,
        dataset,
        human_review,
        dataset_version,
        evaluation_reference,
    )
    thresholds = _validate_threshold_approval(
        reasons,
        threshold_approval,
        evaluation_reference,
    )
    present_case_ids = _validate_cases(reasons, cases)
    required_case_ids = _validate_required_case_ids(
        reasons,
        evaluation_record.get("required_case_ids"),
    )
    if required_case_ids is None:
        required_case_ids = present_case_ids
    for case_id in required_case_ids:
        if case_id not in present_case_ids:
            _add_reason(
                reasons,
                "required_case_missing",
                f"Required dataset case {case_id} is missing.",
                case_id=case_id,
            )
    for case_id in present_case_ids:
        if case_id not in required_case_ids:
            _add_reason(
                reasons,
                "unexpected_dataset_case",
                f"Dataset contains unregistered case {case_id}.",
                case_id=case_id,
            )
    metrics = calculate_metrics(cases, run_records, required_repeats)
    _validate_run_records(
        reasons,
        dataset_version,
        prompt_version,
        approved_models,
        required_case_ids,
        cases,
        run_records,
        required_repeats,
    )
    _validate_metric_thresholds(reasons, thresholds, metrics)
    reasons.sort(
        key=lambda reason: (
            reason["code"],
            reason.get("case_id", ""),
            reason.get("repeat_index", 0),
            reason["message"],
        )
    )
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "metrics": metrics,
    }


def _validate_human_review(
    reasons: list[dict[str, Any]],
    dataset: dict[str, Any],
    human_review: dict[str, Any],
    dataset_version: str | None,
    evaluated_at: datetime,
) -> None:
    if dataset.get("label_status") != "HUMAN_REVIEWED":
        _add_reason(
            reasons,
            "dataset_labels_not_reviewed",
            "Dataset labels are not marked HUMAN_REVIEWED.",
        )
    if human_review.get("status") != "APPROVED":
        _add_reason(
            reasons,
            "human_review_not_approved",
            "Human review status is not APPROVED.",
        )
    raw_reviewers = human_review.get("reviewers")
    reviewers = _identity_list(raw_reviewers)
    if not reviewers:
        _add_reason(
            reasons,
            "reviewer_identities_missing",
            "At least two non-empty reviewer identities are required.",
        )
    elif len(reviewers) < 2:
        _add_reason(
            reasons,
            "reviewer_count_insufficient",
            "At least two distinct reviewer identities are required.",
        )
    if not isinstance(raw_reviewers, list) or any(
        _nonempty_string(item) is None for item in raw_reviewers
    ):
        _add_reason(
            reasons,
            "reviewer_identity_invalid",
            "Reviewer identities must be non-empty strings.",
        )
    if not _valid_approval_date(human_review.get("approved_at"), evaluated_at):
        _add_reason(
            reasons,
            "human_review_date_invalid",
            "Human-review approval date must be a valid, non-future ISO timestamp.",
        )
    adjudication_status = human_review.get("adjudication_status")
    if not _nonempty_string(adjudication_status):
        _add_reason(
            reasons,
            "adjudication_status_missing",
            "Adjudication status is missing.",
        )
    elif adjudication_status not in APPROVED_ADJUDICATION_STATUSES:
        _add_reason(
            reasons,
            "adjudication_incomplete",
            "Disagreement adjudication is not recorded as complete.",
        )
    approved_dataset_version = _nonempty_string(
        human_review.get("approved_dataset_version")
    )
    if approved_dataset_version is None:
        _add_reason(
            reasons,
            "human_review_dataset_version_missing",
            "Human review does not record the approved dataset version.",
        )
    elif dataset_version is not None and approved_dataset_version != dataset_version:
        _add_reason(
            reasons,
            "human_review_dataset_version_mismatch",
            "Human review approval does not match the evaluated dataset version.",
        )


def _validate_threshold_approval(
    reasons: list[dict[str, Any]],
    threshold_approval: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    if threshold_approval.get("status") != "APPROVED":
        _add_reason(
            reasons,
            "thresholds_not_approved",
            "Threshold approval status is not APPROVED.",
        )
    raw_approvers = threshold_approval.get("approved_by")
    approvers = _identity_list(raw_approvers)
    if not approvers:
        _add_reason(
            reasons,
            "threshold_approver_identities_missing",
            "At least one non-empty threshold approver identity is required.",
        )
    if not isinstance(raw_approvers, list) or any(
        _nonempty_string(item) is None for item in raw_approvers
    ):
        _add_reason(
            reasons,
            "threshold_approver_identity_invalid",
            "Threshold approver identities must be non-empty strings.",
        )
    if not _valid_approval_date(
        threshold_approval.get("approved_at"),
        evaluated_at,
    ):
        _add_reason(
            reasons,
            "threshold_approval_date_invalid",
            "Threshold approval date must be a valid, non-future ISO timestamp.",
        )

    thresholds = threshold_approval.get("thresholds")
    if not isinstance(thresholds, dict):
        _add_reason(
            reasons,
            "thresholds_missing",
            "Threshold values are missing or are not an object.",
        )
        return {}
    threshold_keys = set(thresholds)
    string_threshold_keys = {
        key for key in threshold_keys if isinstance(key, str)
    }
    if len(string_threshold_keys) != len(threshold_keys):
        _add_reason(
            reasons,
            "threshold_key_invalid",
            "Threshold names must be strings.",
        )
    for key in sorted(REQUIRED_THRESHOLDS - string_threshold_keys):
        _add_reason(
            reasons,
            "threshold_missing",
            f"Required threshold {key} is missing.",
            threshold=key,
        )
    for key in sorted(string_threshold_keys - REQUIRED_THRESHOLDS):
        _add_reason(
            reasons,
            "threshold_unrecognized",
            f"Threshold {key} is not a recognized evaluation metric.",
            threshold=key,
        )
    valid_thresholds: dict[str, float] = {}
    for key in sorted(REQUIRED_THRESHOLDS & string_threshold_keys):
        value = thresholds[key]
        is_numeric = type(value) in {int, float}
        try:
            is_finite = is_numeric and math.isfinite(value)
        except OverflowError:
            is_finite = type(value) is int
        if not is_finite:
            _add_reason(
                reasons,
                "threshold_value_invalid_type",
                f"Threshold {key} must be a finite JSON number.",
                threshold=key,
            )
        elif not 0 <= value <= 1:
            _add_reason(
                reasons,
                "threshold_value_out_of_range",
                f"Threshold {key} must be in the inclusive range [0, 1].",
                threshold=key,
            )
        else:
            valid_thresholds[key] = float(value)
    return valid_thresholds


def _validate_cases(
    reasons: list[dict[str, Any]],
    cases: list[Any],
) -> list[str]:
    case_ids: list[str] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            _add_reason(
                reasons,
                "dataset_case_malformed",
                f"Dataset case at index {index} is not an object.",
            )
            continue
        case_id = _nonempty_string(case.get("case_id"))
        if case_id is None:
            _add_reason(
                reasons,
                "dataset_case_id_missing",
                f"Dataset case at index {index} has no non-empty identifier.",
            )
        elif case_id in seen:
            _add_reason(
                reasons,
                "dataset_case_id_duplicate",
                f"Dataset case identifier {case_id} is duplicated.",
                case_id=case_id,
            )
        else:
            seen.add(case_id)
            case_ids.append(case_id)
            _validate_case_contents(reasons, case)
    return case_ids


def _validate_required_case_ids(
    reasons: list[dict[str, Any]],
    value: Any,
) -> list[str] | None:
    if not isinstance(value, list) or not value:
        _add_reason(
            reasons,
            "required_case_ids_missing",
            "Evaluation record must declare required case identifiers.",
        )
        return None
    required_ids = []
    seen = set()
    for index, item in enumerate(value):
        case_id = _nonempty_string(item)
        if case_id is None:
            _add_reason(
                reasons,
                "required_case_id_invalid",
                f"Required case identifier at index {index} is invalid.",
            )
        elif case_id in seen:
            _add_reason(
                reasons,
                "required_case_id_duplicate",
                f"Required case identifier {case_id} is duplicated.",
                case_id=case_id,
            )
        else:
            seen.add(case_id)
            required_ids.append(case_id)
    return required_ids


def _validate_case_contents(
    reasons: list[dict[str, Any]],
    case: dict[str, Any],
) -> None:
    case_id = case["case_id"]
    try:
        GoalCriterionDefinition.model_validate(case["criterion"]["definition"])
        expected_result = GoalCriterionResult(case["labels"]["expected_result"])
    except (KeyError, TypeError, ValidationError, ValueError):
        _add_reason(
            reasons,
            "dataset_case_malformed",
            f"Dataset case {case_id} has a malformed criterion or reference label.",
            case_id=case_id,
        )
        return
    labels = case["labels"]
    if _nonempty_string(labels.get("expected_rationale")) is None:
        _add_reason(
            reasons,
            "dataset_case_rationale_missing",
            f"Dataset case {case_id} has no reference rationale.",
            case_id=case_id,
        )
    evidence = case.get("evidence")
    if not isinstance(evidence, list):
        _add_reason(
            reasons,
            "dataset_case_evidence_malformed",
            f"Dataset case {case_id} evidence must be a list.",
            case_id=case_id,
        )
        return
    mapping_ids = []
    for evidence_index, item in enumerate(evidence):
        mapping_id = (
            _nonempty_string(item.get("mapping_id"))
            if isinstance(item, dict)
            else None
        )
        if mapping_id is None:
            _add_reason(
                reasons,
                "dataset_evidence_mapping_id_missing",
                f"Evidence {evidence_index} in case {case_id} has no mapping identifier.",
                case_id=case_id,
            )
        else:
            mapping_ids.append(mapping_id)
    if len(mapping_ids) != len(set(mapping_ids)):
        _add_reason(
            reasons,
            "dataset_evidence_mapping_id_duplicate",
            f"Dataset case {case_id} has duplicate evidence mapping identifiers.",
            case_id=case_id,
        )
    available = set(mapping_ids)
    for label_field in (
        "relevant_supporting_mapping_ids",
        "relevant_contradictory_mapping_ids",
        "expected_supporting_mapping_ids",
        "expected_contradictory_mapping_ids",
    ):
        ids = labels.get(label_field)
        if not isinstance(ids, list) or any(
            not isinstance(mapping_id, str) or not mapping_id.strip()
            for mapping_id in ids
        ):
            _add_reason(
                reasons,
                "dataset_case_reference_ids_malformed",
                f"Reference field {label_field} in case {case_id} must be a list of mapping identifiers.",
                case_id=case_id,
            )
            continue
        if not set(ids) <= available:
            _add_reason(
                reasons,
                "dataset_case_reference_unknown",
                f"Reference field {label_field} in case {case_id} cites evidence outside its context.",
                case_id=case_id,
            )
    expected_support = set(
        _string_list(labels.get("expected_supporting_mapping_ids"))
    )
    expected_contradiction = set(
        _string_list(labels.get("expected_contradictory_mapping_ids"))
    )
    if expected_support.intersection(expected_contradiction):
        _add_reason(
            reasons,
            "dataset_case_reference_conflict",
            f"Dataset case {case_id} marks a mapping as both supporting and contradictory.",
            case_id=case_id,
        )
    if expected_result in ACHIEVEMENT_RESULTS and not expected_support:
        _add_reason(
            reasons,
            "dataset_case_achievement_uncited",
            f"Dataset case {case_id} labels achievement without a supporting citation.",
            case_id=case_id,
        )


def _validate_run_records(
    reasons: list[dict[str, Any]],
    dataset_version: str | None,
    prompt_version: str | None,
    approved_models: list[str],
    case_ids: list[str],
    cases: list[dict[str, Any]],
    run_records: list[dict[str, Any]],
    required_repeats: int,
) -> None:
    cases_by_id = {
        case["case_id"]: case
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    if not isinstance(run_records, list):
        _add_reason(
            reasons,
            "run_records_missing",
            "Evaluation run records are missing or malformed.",
        )
        run_records = []

    for record_index, record in enumerate(run_records):
        if not isinstance(record, dict):
            _add_reason(
                reasons,
                "run_record_malformed",
                f"Run record at index {record_index} is not an object.",
            )
            continue
        case_id = _nonempty_string(record.get("case_id"))
        repeat_index = record.get("repeat_index")
        if case_id is None:
            _add_reason(
                reasons,
                "run_case_id_missing",
                f"Run record at index {record_index} has no case identifier.",
            )
            continue
        if case_id not in cases_by_id:
            _add_reason(
                reasons,
                "run_case_unknown",
                f"Run record references unknown case {case_id}.",
                case_id=case_id,
            )
            continue
        if (
            not isinstance(repeat_index, int)
            or isinstance(repeat_index, bool)
            or not 1 <= repeat_index <= required_repeats
        ):
            _add_reason(
                reasons,
                "run_repeat_index_invalid",
                f"Run for case {case_id} has an invalid repeat index.",
                case_id=case_id,
            )
            continue
        key = (case_id, repeat_index)
        grouped[key].append(record)

        if record.get("status") != "SUCCEEDED":
            code = (
                "run_failed"
                if record.get("status") == "FAILED"
                else "run_status_invalid"
            )
            _add_reason(
                reasons,
                code,
                f"Run {repeat_index} for case {case_id} did not succeed.",
                case_id=case_id,
                repeat_index=repeat_index,
            )
            continue

        if record.get("dataset_version") != dataset_version:
            _add_reason(
                reasons,
                "run_dataset_version_mismatch",
                f"Run {repeat_index} for case {case_id} has a mismatched dataset version.",
                case_id=case_id,
                repeat_index=repeat_index,
            )
        if record.get("prompt_version") != prompt_version:
            _add_reason(
                reasons,
                "run_prompt_version_mismatch",
                f"Run {repeat_index} for case {case_id} has a mismatched prompt version.",
                case_id=case_id,
                repeat_index=repeat_index,
            )
        model_version = _nonempty_string(record.get("model_version"))
        if model_version is None:
            _add_reason(
                reasons,
                "run_model_version_missing",
                f"Run {repeat_index} for case {case_id} has no model version.",
                case_id=case_id,
                repeat_index=repeat_index,
            )
        elif model_version not in approved_models:
            _add_reason(
                reasons,
                "run_model_version_not_approved",
                f"Model version {model_version} used for case {case_id} is not approved.",
                case_id=case_id,
                repeat_index=repeat_index,
            )

        validation_error = _run_validation_error(
            cases_by_id[case_id],
            record,
        )
        if validation_error is not None:
            _add_reason(
                reasons,
                validation_error,
                f"Run {repeat_index} for case {case_id} has an invalid result or citation.",
                case_id=case_id,
                repeat_index=repeat_index,
            )

    for case_id in case_ids:
        for repeat_index in range(1, required_repeats + 1):
            records = grouped.get((case_id, repeat_index), [])
            if not records:
                _add_reason(
                    reasons,
                    "run_missing",
                    f"Run {repeat_index} for case {case_id} is missing.",
                    case_id=case_id,
                    repeat_index=repeat_index,
                )
            elif len(records) > 1:
                _add_reason(
                    reasons,
                    "run_duplicate",
                    f"Run {repeat_index} for case {case_id} is duplicated.",
                    case_id=case_id,
                    repeat_index=repeat_index,
                )


def _run_validation_error(
    case: dict[str, Any],
    record: dict[str, Any],
) -> str | None:
    try:
        proposal = GoalCriterionAssessmentProposal.model_validate(
            {
                "result": record.get("result"),
                "rationale": record.get("rationale"),
                "confidence": record.get("confidence"),
                "supporting_mapping_ids": record.get("supporting_mapping_ids"),
                "contradictory_mapping_ids": record.get(
                    "contradictory_mapping_ids"
                ),
                "completed_milestone_ids": record.get(
                    "completed_milestone_ids", []
                ),
                "measured_value": record.get("measured_value"),
                "limitations": record.get("limitations", []),
            }
        )
        definition = GoalCriterionDefinition.model_validate(
            case["criterion"]["definition"]
        )
    except (KeyError, TypeError, ValidationError):
        return "run_result_malformed"
    available_ids = {
        item.get("mapping_id")
        for item in case.get("evidence", [])
        if isinstance(item, dict) and isinstance(item.get("mapping_id"), str)
    }
    try:
        validate_assessment_citations(proposal, available_ids)
        result, _ = GoalAssessmentService._calculate_progress(
            definition,
            proposal,
        )
        validate_achievement_citation(result, proposal.supporting_mapping_ids)
    except GoalCriterionAssessmentError:
        return "run_citations_invalid"
    return None


def _validate_metric_thresholds(
    reasons: list[dict[str, Any]],
    thresholds: dict[str, Any],
    metrics: dict[str, float | None],
) -> None:
    for threshold_key, metric_key in MINIMUM_THRESHOLD_METRICS.items():
        threshold = thresholds.get(threshold_key)
        if not isinstance(threshold, (int, float)):
            continue
        metric = metrics.get(metric_key)
        if metric is None:
            _add_reason(
                reasons,
                "threshold_metric_unavailable",
                f"Metric {metric_key} is unavailable for its approved threshold.",
                metric=metric_key,
            )
        elif metric < threshold:
            _add_reason(
                reasons,
                "metric_below_threshold",
                f"Metric {metric_key} is below its approved threshold.",
                metric=metric_key,
            )
    for threshold_key, metric_key in MAXIMUM_THRESHOLD_METRICS.items():
        threshold = thresholds.get(threshold_key)
        if not isinstance(threshold, (int, float)):
            continue
        metric = metrics.get(metric_key)
        if metric is None:
            _add_reason(
                reasons,
                "threshold_metric_unavailable",
                f"Metric {metric_key} is unavailable for its approved threshold.",
                metric=metric_key,
            )
        elif metric > threshold:
            _add_reason(
                reasons,
                "metric_above_maximum_threshold",
                f"Metric {metric_key} is above its approved maximum threshold.",
                metric=metric_key,
            )


def _validated_run_output(
    case: dict[str, Any],
    record: dict[str, Any],
) -> tuple[GoalCriterionAssessmentProposal, GoalCriterionResult] | None:
    if record.get("status") != "SUCCEEDED":
        return None
    if _run_validation_error(case, record) is not None:
        return None
    proposal = GoalCriterionAssessmentProposal.model_validate(
        {
            "result": record["result"],
            "rationale": record["rationale"],
            "confidence": record["confidence"],
            "supporting_mapping_ids": record["supporting_mapping_ids"],
            "contradictory_mapping_ids": record["contradictory_mapping_ids"],
            "completed_milestone_ids": record.get(
                "completed_milestone_ids", []
            ),
            "measured_value": record.get("measured_value"),
            "limitations": record.get("limitations", []),
        }
    )
    definition = GoalCriterionDefinition.model_validate(
        case["criterion"]["definition"]
    )
    result, _ = GoalAssessmentService._calculate_progress(definition, proposal)
    return proposal, result


def _valid_approval_date(value: Any, evaluated_at: datetime) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.astimezone(UTC) <= evaluated_at.astimezone(UTC)
    )


def _identity_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    identities = []
    seen = set()
    for item in value:
        identity = _nonempty_string(item)
        if identity is not None and identity.casefold() not in seen:
            identities.append(identity)
            seen.add(identity.casefold())
    return identities


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _nonempty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _add_reason(
    reasons: list[dict[str, Any]],
    code: str,
    message: str,
    **details: Any,
) -> None:
    reason = {"code": code, "message": message, **details}
    if reason not in reasons:
        reasons.append(reason)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
