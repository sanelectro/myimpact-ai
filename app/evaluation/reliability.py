"""Pure comparison and reporting primitives for controlled M6.6.4 runs."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import logging
import re
from enum import StrEnum
from itertools import combinations
from typing import Any, Awaitable, Callable, Mapping, Sequence

from openai import OpenAIError
from pydantic import ValidationError

from app.exceptions import GoalCriterionAssessmentError
from app.models.goal_criteria import (
    GoalCriterionAssessmentProposal,
    GoalCriterionDefinition,
)
from app.models.llm import LLMRequest
from app.services.goal_assessment import (
    ASSESSMENT_PROMPT_VERSION,
    GoalAssessmentService,
    build_criterion_assessment_prompt,
    normalize_assessment_response,
    validate_achievement_citation,
    validate_assessment_citations,
)
from app.services.llm.interface import ILLMService
from app.config.settings import get_settings


NORMALIZATION_VERSION = "m66-reliability-normalization-v1"
COMPARISON_VERSION = "m66-reliability-comparison-v1"
CATEGORY_ASSESSMENT_PROMPT_VERSION = "m66-category-assessment-v1"
logger = logging.getLogger(__name__)


class ComparisonStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class DifferenceCategory(StrEnum):
    MODEL_OUTPUT_VARIATION = "MODEL_OUTPUT_VARIATION"
    RETRIEVAL_VARIATION = "RETRIEVAL_VARIATION"
    SOURCE_CONTENT_CHANGED = "SOURCE_CONTENT_CHANGED"
    CONFIGURATION_MISMATCH = "CONFIGURATION_MISMATCH"
    SCHEMA_OR_PARSING_FAILURE = "SCHEMA_OR_PARSING_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    UNKNOWN = "UNKNOWN"


class ThresholdResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUABLE = "NOT_EVALUABLE"


@dataclass(frozen=True)
class NormalizedOutput:
    assessment_label: str
    supporting_evidence_ids: tuple[str, ...]
    contradictory_evidence_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    abstained: bool
    structured_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "assessment_label": self.assessment_label,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradictory_evidence_ids": list(self.contradictory_evidence_ids),
            "citation_ids": list(self.citation_ids),
            "abstained": self.abstained,
            "structured_status": self.structured_status,
        }


@dataclass(frozen=True)
class NormalizationResult:
    output: NormalizedOutput | None
    valid: bool
    error: str | None = None


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    case_id: str
    sequence: int
    status: str
    raw_output: Mapping[str, Any] | None = None
    normalized_output: NormalizedOutput | None = None
    schema_valid: bool = False
    error_category: str | None = None
    error_detail: str | None = None
    input_fingerprint: str | None = None
    model_identifier: str | None = None
    configuration_fingerprint: str | None = None
    retrieval_fingerprint: str | None = None
    source_snapshot_id: str | None = None


@dataclass(frozen=True)
class ReliabilityExperimentConfig:
    dataset_id: str
    dataset_version: str
    prompt_version: str
    model_identifier: str
    model_configuration: Mapping[str, Any]
    retrieval_configuration_version: str
    source_snapshot_id: str | None
    evaluation_code_version: str
    output_schema_version: str
    normalization_version: str = NORMALIZATION_VERSION
    repetitions_per_case: int = 3
    case_selection: tuple[str, ...] | None = None
    max_retries: int = 0

    def validate(self, dataset: Mapping[str, Any]) -> tuple[str, ...]:
        errors: list[str] = []
        required_fields = {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "prompt_version": self.prompt_version,
            "model_identifier": self.model_identifier,
            "retrieval_configuration_version": self.retrieval_configuration_version,
            "evaluation_code_version": self.evaluation_code_version,
            "output_schema_version": self.output_schema_version,
            "normalization_version": self.normalization_version,
        }
        errors.extend(
            f"{field} is required."
            for field, value in required_fields.items()
            if not isinstance(value, str) or not value.strip()
        )
        if self.repetitions_per_case < 1:
            errors.append("repetitions_per_case must be positive.")
        if self.max_retries < 0:
            errors.append("max_retries cannot be negative.")
        if self.prompt_version not in {
            ASSESSMENT_PROMPT_VERSION,
            CATEGORY_ASSESSMENT_PROMPT_VERSION,
        }:
            errors.append("prompt_version does not match the active assessment prompt.")
        if dataset.get("dataset_id") != self.dataset_id:
            errors.append("dataset_id does not match the selected dataset.")
        record = dataset.get("evaluation_record")
        if not isinstance(record, Mapping) or record.get("dataset_version") != self.dataset_version:
            errors.append("dataset_version does not match the selected dataset.")
        available_case_ids = {
            case.get("case_id")
            for case in dataset.get("cases", [])
            if isinstance(case, Mapping)
        }
        selected_case_ids = self.case_selection or tuple(sorted(available_case_ids))
        if not selected_case_ids:
            errors.append("case_selection cannot be empty.")
        if len(set(selected_case_ids)) != len(selected_case_ids):
            errors.append("case_selection must not contain duplicates.")
        if set(selected_case_ids) - available_case_ids:
            errors.append("case_selection contains an unknown case.")
        return tuple(errors)


@dataclass(frozen=True)
class ReliabilityRun:
    experiment_id: str
    config: ReliabilityExperimentConfig
    attempts: tuple[Attempt, ...]
    report: ReliabilityReport


@dataclass(frozen=True)
class DimensionMetric:
    numerator: int
    denominator: int
    value: float | None
    cases_included: int
    cases_excluded: int
    aggregation: str


@dataclass(frozen=True)
class CaseComparison:
    case_id: str
    status: ComparisonStatus
    attempt_ids: tuple[str, ...]
    valid_attempt_ids: tuple[str, ...]
    label_metric: DimensionMetric
    evidence_metric: DimensionMetric
    citation_metric: DimensionMetric
    abstention_metric: DimensionMetric
    exact_output_consistent: bool | None
    distinct_labels: tuple[str, ...]
    label_tie: bool
    difference_categories: tuple[DifferenceCategory, ...]
    differences: tuple[dict[str, Any], ...]
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ReliabilityReport:
    report_version: str
    experiment_id: str
    normalization_version: str
    comparison_version: str
    planned_attempts: int
    completed_attempts: int
    failed_attempts: int
    invalid_attempts: int
    incomplete_cases: int
    metrics: Mapping[str, DimensionMetric]
    comparisons: tuple[CaseComparison, ...]
    threshold_result: ThresholdResult
    threshold_details: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


def normalize_output(raw_output: Mapping[str, Any] | None) -> NormalizationResult:
    """Normalize semantic assessment fields while rejecting malformed output."""
    if not isinstance(raw_output, Mapping):
        return NormalizationResult(None, False, "Output is not an object.")

    result = raw_output.get("result")
    if hasattr(result, "value"):
        result = result.value
    if not isinstance(result, str) or not result:
        return NormalizationResult(None, False, "Output result is missing.")

    supporting = _string_tuple(raw_output.get("supporting_mapping_ids"))
    contradictory = _string_tuple(raw_output.get("contradictory_mapping_ids"))
    if supporting is None or contradictory is None:
        return NormalizationResult(
            None,
            False,
            "Evidence mapping IDs must be arrays of strings.",
        )
    if set(supporting) & set(contradictory):
        return NormalizationResult(
            None,
            False,
            "An evidence mapping cannot be both supporting and contradictory.",
        )

    citations = raw_output.get("citation_ids")
    if citations is None:
        citations = supporting + contradictory
    citation_ids = _string_tuple(citations)
    if citation_ids is None:
        return NormalizationResult(
            None,
            False,
            "Citation IDs must be an array of strings.",
        )

    status = raw_output.get("structured_status", "VALID")
    if not isinstance(status, str) or not status:
        return NormalizationResult(None, False, "Structured status is missing.")

    output = NormalizedOutput(
        assessment_label=result,
        supporting_evidence_ids=tuple(sorted(set(supporting))),
        contradictory_evidence_ids=tuple(sorted(set(contradictory))),
        citation_ids=tuple(sorted(set(citation_ids))),
        abstained=bool(raw_output.get("abstained", result == "NEEDS_REVIEW")),
        structured_status=status,
    )
    return NormalizationResult(output, True)


def compare_case(
    case_id: str,
    attempts: Sequence[Attempt],
    *,
    planned_repetitions: int,
) -> CaseComparison:
    """Compare one case without treating invalid or missing attempts as matches."""
    ordered = sorted(attempts, key=lambda attempt: attempt.sequence)
    valid = [
        attempt
        for attempt in ordered
        if attempt.status == "SUCCEEDED"
        and attempt.schema_valid
        and attempt.normalized_output is not None
    ]
    exclusions: list[str] = []
    if len(ordered) != planned_repetitions:
        exclusions.append(
            f"Expected {planned_repetitions} attempts but received {len(ordered)}."
        )
    if len({attempt.sequence for attempt in ordered}) != len(ordered):
        exclusions.append("Attempt sequence numbers are not unique.")
    exclusions.extend(
        f"{attempt.attempt_id}: {attempt.error_detail or attempt.status}"
        for attempt in ordered
        if attempt not in valid
    )

    labels = [
        attempt.normalized_output.assessment_label
        for attempt in valid
        if attempt.normalized_output
    ]
    label_counts = Counter(labels)
    largest_count = max(label_counts.values(), default=0)
    label_tie = (
        len([count for count in label_counts.values() if count == largest_count]) > 1
        and largest_count > 0
    )
    complete = len(ordered) == planned_repetitions and len(valid) == planned_repetitions
    label_metric = _metric(
        largest_count,
        len(labels),
        1 if labels else 0,
        0 if labels else 1,
        "majority label share across valid attempts",
    )
    evidence_metric = _pairwise_set_metric(
        valid,
        lambda output: set(output.supporting_evidence_ids)
        | set(output.contradictory_evidence_ids),
    )
    citation_metric = _pairwise_set_metric(
        valid,
        lambda output: set(output.citation_ids),
    )
    abstention_values = [
        attempt.normalized_output.abstained
        for attempt in valid
        if attempt.normalized_output
    ]
    abstention_metric = _metric(
        sum(value == abstention_values[0] for value in abstention_values)
        if abstention_values
        else 0,
        len(abstention_values),
        1 if abstention_values else 0,
        0 if abstention_values else 1,
        "agreement with the first valid abstention decision",
    )
    normalized_values = [
        attempt.normalized_output.as_dict()
        for attempt in valid
        if attempt.normalized_output
    ]
    exact = (
        bool(complete and normalized_values)
        and len({repr(value) for value in normalized_values}) == 1
    )
    differences = _differences(valid)
    categories = _difference_categories(ordered, valid, differences)
    return CaseComparison(
        case_id=case_id,
        status=ComparisonStatus.COMPLETE if complete else ComparisonStatus.INCOMPLETE,
        attempt_ids=tuple(attempt.attempt_id for attempt in ordered),
        valid_attempt_ids=tuple(attempt.attempt_id for attempt in valid),
        label_metric=label_metric,
        evidence_metric=evidence_metric,
        citation_metric=citation_metric,
        abstention_metric=abstention_metric,
        exact_output_consistent=exact if complete else None,
        distinct_labels=tuple(sorted(label_counts)),
        label_tie=label_tie,
        difference_categories=categories,
        differences=differences,
        exclusion_reasons=tuple(exclusions),
    )


def build_reliability_report(
    experiment_id: str,
    attempts: Sequence[Attempt],
    *,
    case_ids: Sequence[str],
    planned_repetitions: int,
    threshold_set: Mapping[str, Any] | None = None,
    experiment_identity: Mapping[str, Any] | None = None,
) -> ReliabilityReport:
    """Build a reproducible report from stored attempts and pinned metadata."""
    by_case = {case_id: [] for case_id in case_ids}
    for attempt in attempts:
        if attempt.case_id in by_case:
            by_case[attempt.case_id].append(attempt)
    comparisons = tuple(
        compare_case(
            case_id,
            by_case[case_id],
            planned_repetitions=planned_repetitions,
        )
        for case_id in case_ids
    )
    complete = [comparison for comparison in comparisons if comparison.status == ComparisonStatus.COMPLETE]
    metrics = {
        "label_consistency": _aggregate_metric(
            [comparison.label_metric for comparison in complete]
        ),
        "evidence_selection_consistency": _aggregate_metric(
            [comparison.evidence_metric for comparison in complete]
        ),
        "citation_set_consistency": _aggregate_metric(
            [comparison.citation_metric for comparison in complete]
        ),
        "abstention_consistency": _aggregate_metric(
            [comparison.abstention_metric for comparison in complete]
        ),
        "structured_output_validity": _metric(
            sum(attempt.schema_valid and attempt.status == "SUCCEEDED" for attempt in attempts),
            len(attempts),
            len({attempt.case_id for attempt in attempts}),
            0,
            "valid attempts divided by all recorded attempts",
        ),
        "exact_output_consistency": _metric(
            sum(comparison.exact_output_consistent is True for comparison in complete),
            len(complete),
            len(complete),
            len(comparisons) - len(complete),
            "complete cases with identical normalized output",
        ),
        "repeatability": _metric(
            sum(comparison.exact_output_consistent is True for comparison in complete),
            len(complete),
            len(complete),
            len(comparisons) - len(complete),
            "strict exact normalized-output consistency across complete cases",
        ),
        "run_success_rate": _metric(
            sum(
                attempt.status == "SUCCEEDED" and attempt.schema_valid
                for attempt in attempts
            ),
            len(attempts),
            len({attempt.case_id for attempt in attempts}),
            0,
            "valid successful attempts divided by all recorded attempts",
        ),
    }
    threshold_result, threshold_details = compare_thresholds(
        metrics,
        threshold_set,
        experiment_identity=experiment_identity,
    )
    return ReliabilityReport(
        report_version="m66-reliability-report-v1",
        experiment_id=experiment_id,
        normalization_version=NORMALIZATION_VERSION,
        comparison_version=COMPARISON_VERSION,
        planned_attempts=len(case_ids) * planned_repetitions,
        completed_attempts=sum(attempt.status == "SUCCEEDED" for attempt in attempts),
        failed_attempts=sum(attempt.status == "FAILED" for attempt in attempts),
        invalid_attempts=sum(
            attempt.status == "SUCCEEDED" and not attempt.schema_valid
            for attempt in attempts
        ),
        incomplete_cases=len(comparisons) - len(complete),
        metrics=metrics,
        comparisons=comparisons,
        threshold_result=threshold_result,
        threshold_details=threshold_details,
        limitations=(
            "Consistency is reported separately from correctness.",
            "Citation stability does not establish citation validity or support.",
            "A missing or invalid attempt prevents a case from passing comparison.",
        ),
    )


async def run_reliability_experiment(
    llm_service: ILLMService,
    dataset: Mapping[str, Any],
    *,
    experiment_id: str,
    config: ReliabilityExperimentConfig,
    threshold_set: Mapping[str, Any] | None = None,
    on_attempt: Callable[[Attempt], Awaitable[None]] | None = None,
) -> ReliabilityRun:
    """Execute pinned repeated attempts and build a report from their outputs."""
    errors = config.validate(dataset)
    if errors:
        raise ValueError("; ".join(errors))
    cases_by_id = {
        case["case_id"]: case
        for case in dataset["cases"]
        if isinstance(case, Mapping) and isinstance(case.get("case_id"), str)
    }
    case_ids = config.case_selection or tuple(sorted(cases_by_id))
    input_fingerprint = _fingerprint(
        {
            "dataset_version": config.dataset_version,
            "prompt_version": config.prompt_version,
            "retrieval_configuration_version": config.retrieval_configuration_version,
            "source_snapshot_id": config.source_snapshot_id,
            "case_ids": case_ids,
        }
    )
    attempts: list[Attempt] = []
    last_attempt_finished_at: float | None = None
    for case_id in case_ids:
        case = cases_by_id[case_id]
        criterion = case["criterion"]
        definition = GoalCriterionDefinition.model_validate(criterion["definition"])
        prompt = build_criterion_assessment_prompt(
            criterion_id=criterion["id"],
            criterion_version_id=criterion["version_id"],
            criterion_version=criterion["version"],
            definition=definition,
            evidence_inputs=case["evidence"],
            retrieval_sufficient=case["retrieval_sufficient"],
            role_context=case.get("role_context"),
            evaluation_period=case.get("evaluation_period"),
        )
        prompt = _append_category_instruction(prompt, case)
        mapping_ids = {item["mapping_id"] for item in case["evidence"]}
        for sequence in range(1, config.repetitions_per_case + 1):
            if last_attempt_finished_at is not None:
                elapsed = asyncio.get_running_loop().time() - last_attempt_finished_at
                interval = get_settings().llm_min_interval_seconds
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)
            logger.info(
                "Starting reliability attempt experiment_id=%s case_id=%s sequence=%s/%s",
                experiment_id,
                case_id,
                sequence,
                config.repetitions_per_case,
            )
            attempt = await _run_attempt(
                llm_service,
                prompt=prompt,
                mapping_ids=mapping_ids,
                definition=definition,
                experiment_id=experiment_id,
                case_id=case_id,
                sequence=sequence,
                config=config,
                input_fingerprint=input_fingerprint,
            )
            attempts.append(attempt)
            last_attempt_finished_at = asyncio.get_running_loop().time()
            logger.info(
                "Finished reliability attempt experiment_id=%s case_id=%s sequence=%s/%s status=%s",
                experiment_id,
                case_id,
                sequence,
                config.repetitions_per_case,
                attempt.status,
            )
            if on_attempt is not None:
                await on_attempt(attempt)
    report = build_reliability_report(
        experiment_id,
        attempts,
        case_ids=case_ids,
        planned_repetitions=config.repetitions_per_case,
        threshold_set=threshold_set,
        experiment_identity={
            "dataset_id": config.dataset_id,
            "dataset_version": config.dataset_version,
            "prompt_version": config.prompt_version,
            "model_identifier": config.model_identifier,
            "model_configuration": dict(config.model_configuration),
            "evaluation_code_version": config.evaluation_code_version,
        },
    )
    return ReliabilityRun(experiment_id, config, tuple(attempts), report)


def _append_category_instruction(prompt: str, case: Mapping[str, Any]) -> str:
    mapping = case.get("ai_label_map")
    options = case.get("review_label_options")
    category = case.get("category")
    if not isinstance(category, str) or not isinstance(mapping, Mapping):
        return prompt
    category_labels = ", ".join(str(option) for option in options or [])
    output_mapping = ", ".join(
        f"{ai_label} means {human_label}"
        for ai_label, human_label in mapping.items()
    )
    return (
        f"{prompt}\n\n"
        f"This is a {category} benchmark case. Human answer options are: "
        f"{category_labels}. Use the existing backend result field, but apply "
        f"this category mapping when choosing the result: {output_mapping}. "
        "Return MET for a supported positive conclusion, NOT_STARTED for a "
        "supported negative conclusion, and NEEDS_REVIEW when the evidence "
        "does not support a reliable conclusion. Do not invent evidence."
    )


async def _run_attempt(
    llm_service: ILLMService,
    *,
    prompt: str,
    mapping_ids: set[str],
    definition: GoalCriterionDefinition,
    experiment_id: str,
    case_id: str,
    sequence: int,
    config: ReliabilityExperimentConfig,
    input_fingerprint: str,
) -> Attempt:
    last_error: Exception | None = None
    for _retry_index in range(config.max_retries + 1):
        try:
            response = await asyncio.wait_for(
                llm_service.generate(
                    LLMRequest(
                        prompt=prompt,
                        response_format={"type": "json_object"},
                    )
                ),
                timeout=get_settings().llm_timeout_seconds,
            )
            normalized_json = normalize_assessment_response(response.content)
            proposal = GoalCriterionAssessmentProposal.model_validate_json(
                normalized_json
            )
            validate_assessment_citations(proposal, mapping_ids)
            assessed_result, _ = GoalAssessmentService._calculate_progress(
                definition,
                proposal,
            )
            validate_achievement_citation(
                assessed_result,
                proposal.supporting_mapping_ids,
            )
            raw_output = proposal.model_dump(mode="json")
            raw_output["result"] = assessed_result.value
            normalized = normalize_output(raw_output)
            if not normalized.valid or normalized.output is None:
                raise ValueError(normalized.error or "Normalized output is invalid.")
            return Attempt(
                attempt_id=_attempt_identifier(experiment_id, case_id, sequence),
                case_id=case_id,
                sequence=sequence,
                status="SUCCEEDED",
                raw_output=raw_output,
                normalized_output=normalized.output,
                schema_valid=True,
                input_fingerprint=input_fingerprint,
                model_identifier=response.model or config.model_identifier,
                configuration_fingerprint=_fingerprint(config.model_configuration),
                retrieval_fingerprint=config.retrieval_configuration_version,
                source_snapshot_id=config.source_snapshot_id,
            )
        except (
            OpenAIError,
            TimeoutError,
            ValidationError,
            GoalCriterionAssessmentError,
            ValueError,
        ) as exc:
            last_error = exc
            if _is_rate_limit_error(exc) and _retry_index < config.max_retries:
                delay = _rate_limit_delay_seconds(exc)
                logger.warning(
                    "Provider rate limit for case_id=%s sequence=%s; retrying in %.1fs",
                    case_id,
                    sequence,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            if not isinstance(exc, (OpenAIError, TimeoutError)):
                break
    assert last_error is not None
    return Attempt(
        attempt_id=_attempt_identifier(experiment_id, case_id, sequence),
        case_id=case_id,
        sequence=sequence,
        status="FAILED",
        schema_valid=False,
        error_category=_error_category(last_error),
        error_detail=str(last_error)[:1000],
        input_fingerprint=input_fingerprint,
        model_identifier=config.model_identifier,
        configuration_fingerprint=_fingerprint(config.model_configuration),
        retrieval_fingerprint=config.retrieval_configuration_version,
        source_snapshot_id=config.source_snapshot_id,
    )


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _attempt_identifier(experiment_id: str, case_id: str, sequence: int) -> str:
    identity = _fingerprint(
        {"experiment_id": experiment_id, "case_id": case_id, "sequence": sequence}
    )
    return f"{experiment_id[:8]}-{identity[:24]}"


def _error_category(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return "TIMEOUT"
    if isinstance(error, OpenAIError):
        return "PROVIDER_ERROR"
    if isinstance(error, ValidationError):
        return "SCHEMA_OR_PARSING_FAILURE"
    if isinstance(error, GoalCriterionAssessmentError):
        return "VALIDATION_ERROR"
    return "EXECUTION_FAILURE"


def _is_rate_limit_error(error: Exception) -> bool:
    return getattr(error, "status_code", None) == 429 or "429" in str(error)


def _rate_limit_delay_seconds(error: Exception) -> float:
    headers = getattr(error, "headers", None)
    if headers:
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        try:
            return max(float(retry_after), 1.0)
        except (TypeError, ValueError):
            pass
    match = re.search(r"try again in ([0-9]+(?:\.[0-9]+)?)s", str(error))
    if match:
        return max(float(match.group(1)), 1.0)
    return 6.0


def compare_thresholds(
    metrics: Mapping[str, DimensionMetric],
    threshold_set: Mapping[str, Any] | None,
    *,
    experiment_identity: Mapping[str, Any] | None = None,
) -> tuple[ThresholdResult, tuple[dict[str, Any], ...]]:
    """Apply only a compatible approved threshold set; otherwise fail closed."""
    if not threshold_set or threshold_set.get("status") != "APPROVED":
        return ThresholdResult.NOT_EVALUABLE, (
            {"reason": "No approved compatible threshold set is available."},
        )
    compatibility_fields = (
        "dataset_id",
        "dataset_version",
        "prompt_version",
        "model_identifier",
        "evaluation_code_version",
    )
    if experiment_identity is None or any(
        threshold_set.get(field) != experiment_identity.get(field)
        for field in compatibility_fields
    ):
        return ThresholdResult.NOT_EVALUABLE, (
            {"reason": "Approved threshold set is incompatible with the experiment."},
        )
    if threshold_set.get("model_configuration") != experiment_identity.get(
        "model_configuration"
    ):
        return ThresholdResult.NOT_EVALUABLE, (
            {"reason": "Approved threshold model configuration is incompatible."},
        )
    items = threshold_set.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
        return ThresholdResult.NOT_EVALUABLE, ({"reason": "Threshold items are missing."},)
    details: list[dict[str, Any]] = []
    overall = ThresholdResult.PASS
    for item in items:
        if not isinstance(item, Mapping):
            return ThresholdResult.NOT_EVALUABLE, ({"reason": "Threshold item is invalid."},)
        metric_id = item.get("metric_id")
        metric = metrics.get(metric_id)
        threshold = item.get("threshold_value")
        operator = item.get("operator")
        if metric is None or metric.value is None or not isinstance(threshold, (int, float)):
            details.append({"metric_id": metric_id, "status": ThresholdResult.NOT_EVALUABLE})
            overall = ThresholdResult.NOT_EVALUABLE
            continue
        passed = (
            metric.value >= threshold if operator == ">="
            else metric.value <= threshold if operator == "<="
            else False
        )
        status = ThresholdResult.PASS if passed else ThresholdResult.FAIL
        details.append(
            {
                "metric_id": metric_id,
                "threshold": threshold,
                "operator": operator,
                "value": metric.value,
                "numerator": metric.numerator,
                "denominator": metric.denominator,
                "status": status,
            }
        )
        if status == ThresholdResult.FAIL:
            overall = ThresholdResult.FAIL
    return overall, tuple(details)


def _string_tuple(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) and item for item in value
    ):
        return None
    return tuple(value)


def _metric(
    numerator: int,
    denominator: int,
    cases_included: int,
    cases_excluded: int,
    aggregation: str,
) -> DimensionMetric:
    return DimensionMetric(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator if denominator else None,
        cases_included=cases_included,
        cases_excluded=cases_excluded,
        aggregation=aggregation,
    )


def _pairwise_set_metric(
    attempts: Sequence[Attempt],
    selector: Any,
) -> DimensionMetric:
    outputs = [
        attempt.normalized_output
        for attempt in attempts
        if attempt.normalized_output is not None
    ]
    pairs = list(combinations(outputs, 2))
    scores = [
        _jaccard(selector(left), selector(right))
        for left, right in pairs
    ]
    if not scores:
        return _metric(0, 0, 0, 1, "macro-average pairwise Jaccard")
    numerator = sum(scores)
    denominator = len(scores)
    return DimensionMetric(
        numerator=round(numerator * 1_000_000),
        denominator=denominator * 1_000_000,
        value=numerator / denominator,
        cases_included=1,
        cases_excluded=0,
        aggregation="macro-average pairwise Jaccard",
    )


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _aggregate_metric(metrics: Sequence[DimensionMetric]) -> DimensionMetric:
    available = [metric for metric in metrics if metric.value is not None]
    numerator = sum(metric.numerator for metric in available)
    denominator = sum(metric.denominator for metric in available)
    return _metric(
        numerator,
        denominator,
        len(available),
        len(metrics) - len(available),
        "weighted aggregate of case comparison numerators and denominators",
    )


def _differences(
    valid: Sequence[Attempt],
) -> tuple[dict[str, Any], ...]:
    differences: list[dict[str, Any]] = []
    for left, right in combinations(valid, 2):
        if left.normalized_output == right.normalized_output:
            continue
        differences.append(
            {
                "attempt_ids": [left.attempt_id, right.attempt_id],
                "left": left.normalized_output.as_dict() if left.normalized_output else None,
                "right": right.normalized_output.as_dict() if right.normalized_output else None,
            }
        )
    return tuple(differences)


def _difference_categories(
    ordered: Sequence[Attempt],
    valid: Sequence[Attempt],
    differences: Sequence[dict[str, Any]],
) -> tuple[DifferenceCategory, ...]:
    categories: set[DifferenceCategory] = set()
    if any(attempt.status == "FAILED" for attempt in ordered):
        categories.add(DifferenceCategory.EXECUTION_FAILURE)
    if any(not attempt.schema_valid for attempt in ordered):
        categories.add(DifferenceCategory.SCHEMA_OR_PARSING_FAILURE)
    if valid and any(
        attempt.configuration_fingerprint != valid[0].configuration_fingerprint
        for attempt in valid[1:]
    ):
        categories.add(DifferenceCategory.CONFIGURATION_MISMATCH)
    if valid and any(
        attempt.model_identifier != valid[0].model_identifier
        for attempt in valid[1:]
    ):
        categories.add(DifferenceCategory.CONFIGURATION_MISMATCH)
    if valid and any(
        attempt.retrieval_fingerprint != valid[0].retrieval_fingerprint
        for attempt in valid[1:]
    ):
        categories.add(DifferenceCategory.RETRIEVAL_VARIATION)
    if valid and any(
        attempt.source_snapshot_id != valid[0].source_snapshot_id
        for attempt in valid[1:]
    ):
        categories.add(DifferenceCategory.SOURCE_CONTENT_CHANGED)
    if differences and not categories:
        categories.add(DifferenceCategory.MODEL_OUTPUT_VARIATION)
    return tuple(sorted(categories, key=lambda category: category.value))
