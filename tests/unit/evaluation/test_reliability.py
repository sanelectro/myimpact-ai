from app.evaluation.reliability import (
    ComparisonStatus,
    DifferenceCategory,
    ThresholdResult,
    Attempt,
    ReliabilityExperimentConfig,
    build_reliability_report,
    compare_case,
    normalize_output,
    run_reliability_experiment,
)
from app.evaluation.assessment_evaluation import load_dataset
from app.models.llm import LLMResponse
from app.services.goal_assessment import ASSESSMENT_PROMPT_VERSION
import asyncio
import json


def _attempt(
    attempt_id: str,
    sequence: int,
    *,
    result: str = "MET",
    supporting: list[str] | None = None,
    citation_ids: list[str] | None = None,
    status: str = "SUCCEEDED",
    schema_valid: bool = True,
    retrieval: str | None = "retrieval-v1",
):
    raw = {
        "result": result,
        "supporting_mapping_ids": supporting or [],
        "contradictory_mapping_ids": [],
    }
    if citation_ids is not None:
        raw["citation_ids"] = citation_ids
    normalized = normalize_output(raw)
    return Attempt(
        attempt_id=attempt_id,
        case_id="case-1",
        sequence=sequence,
        status=status,
        raw_output=raw,
        normalized_output=normalized.output,
        schema_valid=schema_valid and normalized.valid,
        error_detail=None if normalized.valid else normalized.error,
        retrieval_fingerprint=retrieval,
    )


def test_normalization_is_order_insensitive_and_defaults_citations():
    result = normalize_output(
        {
            "result": "MET",
            "supporting_mapping_ids": ["b", "a", "a"],
            "contradictory_mapping_ids": [],
        }
    )

    assert result.valid is True
    assert result.output is not None
    assert result.output.supporting_evidence_ids == ("a", "b")
    assert result.output.citation_ids == ("a", "b")


def test_invalid_output_is_explicit():
    result = normalize_output(
        {
            "result": "MET",
            "supporting_mapping_ids": ["same"],
            "contradictory_mapping_ids": ["same"],
        }
    )

    assert result.valid is False
    assert "both supporting and contradictory" in (result.error or "")


def test_case_reports_label_and_evidence_differences_separately():
    comparison = compare_case(
        "case-1",
        [
            _attempt("a1", 1, result="MET", supporting=["e1"]),
            _attempt("a2", 2, result="IN_PROGRESS", supporting=["e2"]),
            _attempt("a3", 3, result="MET", supporting=["e1"]),
        ],
        planned_repetitions=3,
    )

    assert comparison.status == ComparisonStatus.COMPLETE
    assert comparison.label_metric.value == 2 / 3
    assert comparison.evidence_metric.value == (0 + 1 + 0) / 3
    assert comparison.label_tie is False
    assert comparison.difference_categories == (
        DifferenceCategory.MODEL_OUTPUT_VARIATION,
    )


def test_failed_attempt_makes_comparison_incomplete_and_never_consistent():
    comparison = compare_case(
        "case-1",
        [
            _attempt("a1", 1),
            _attempt(
                "a2",
                2,
                status="FAILED",
                schema_valid=False,
            ),
        ],
        planned_repetitions=3,
    )

    assert comparison.status == ComparisonStatus.INCOMPLETE
    assert comparison.exact_output_consistent is None
    assert DifferenceCategory.EXECUTION_FAILURE in comparison.difference_categories
    assert DifferenceCategory.SCHEMA_OR_PARSING_FAILURE in comparison.difference_categories


def test_report_is_exploratory_without_approved_thresholds():
    report = build_reliability_report(
        "experiment-1",
        [
            _attempt("a1", 1),
            _attempt("a2", 2),
            _attempt("a3", 3),
        ],
        case_ids=["case-1"],
        planned_repetitions=3,
    )

    assert report.metrics["exact_output_consistency"].value == 1.0
    assert report.threshold_result == ThresholdResult.NOT_EVALUABLE


def test_approved_thresholds_are_applied_with_denominators():
    report = build_reliability_report(
        "experiment-1",
        [
            _attempt("a1", 1),
            _attempt("a2", 2),
            _attempt("a3", 3),
        ],
        case_ids=["case-1"],
        planned_repetitions=3,
        threshold_set={
            "status": "APPROVED",
            "dataset_id": "dataset-1",
            "dataset_version": "dataset-v1",
            "prompt_version": ASSESSMENT_PROMPT_VERSION,
            "model_identifier": "fixture-model",
            "model_configuration": {"temperature": 0},
            "evaluation_code_version": "test-code",
            "items": [
                {
                    "metric_id": "exact_output_consistency",
                    "operator": ">=",
                    "threshold_value": 1.0,
                }
            ],
        },
        experiment_identity={
            "dataset_id": "dataset-1",
            "dataset_version": "dataset-v1",
            "prompt_version": ASSESSMENT_PROMPT_VERSION,
            "model_identifier": "fixture-model",
            "model_configuration": {"temperature": 0},
            "evaluation_code_version": "test-code",
        },
    )

    assert report.threshold_result == ThresholdResult.PASS
    assert report.threshold_details[0]["numerator"] == 1
    assert report.threshold_details[0]["denominator"] == 1


def _config(dataset, *, repetitions=3, max_retries=0):
    return ReliabilityExperimentConfig(
        dataset_id=dataset["dataset_id"],
        dataset_version=dataset["evaluation_record"]["dataset_version"],
        prompt_version=ASSESSMENT_PROMPT_VERSION,
        model_identifier="fixture-model",
        model_configuration={"temperature": 0},
        retrieval_configuration_version="retrieval-v1",
        source_snapshot_id="snapshot-v1",
        evaluation_code_version="test-code",
        output_schema_version="assessment-v1",
        repetitions_per_case=repetitions,
        case_selection=(dataset["cases"][0]["case_id"],),
        max_retries=max_retries,
    )


class _FixtureLLM:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    async def generate(self, _request):
        self.calls += 1
        if self.error:
            raise self.error
        return LLMResponse(content=json.dumps(self.response), model="fixture-model")


def test_controlled_runner_records_pinned_attempts_and_builds_report():
    dataset = load_dataset()
    case = dataset["cases"][0]
    labels = case["labels"]
    llm = _FixtureLLM(
        {
            "result": labels["expected_result"],
            "rationale": labels["expected_rationale"],
            "confidence": 0.8,
            "supporting_mapping_ids": labels["expected_supporting_mapping_ids"],
            "contradictory_mapping_ids": labels["expected_contradictory_mapping_ids"],
            "completed_milestone_ids": [],
            "measured_value": labels["expected_measured_value"],
            "limitations": [],
        }
    )

    run = asyncio.run(
        run_reliability_experiment(
            llm,
            dataset,
            experiment_id="experiment-1",
            config=_config(dataset),
        )
    )

    assert llm.calls == 3
    assert len(run.attempts) == 3
    assert {attempt.sequence for attempt in run.attempts} == {1, 2, 3}
    assert all(attempt.schema_valid for attempt in run.attempts)
    assert run.report.metrics["exact_output_consistency"].value == 1.0
    assert run.report.threshold_result == ThresholdResult.NOT_EVALUABLE


def test_runner_preserves_provider_failures_and_retries_only_within_bound():
    dataset = load_dataset()
    dataset["cases"] = [dataset["cases"][0]]
    llm = _FixtureLLM(None, TimeoutError("provider timed out"))

    run = asyncio.run(
        run_reliability_experiment(
            llm,
            dataset,
            experiment_id="experiment-1",
            config=_config(dataset, repetitions=1, max_retries=1),
        )
    )

    assert llm.calls == 2
    assert run.attempts[0].status == "FAILED"
    assert run.attempts[0].error_category == "TIMEOUT"
    assert run.report.incomplete_cases == 1
    assert run.report.threshold_result == ThresholdResult.NOT_EVALUABLE


def test_runner_times_out_hanging_provider_call(monkeypatch):
    dataset = load_dataset()
    dataset["cases"] = [dataset["cases"][0]]

    class HangingLLM:
        async def generate(self, _request):
            await asyncio.sleep(10)

    monkeypatch.setattr(
        "app.evaluation.reliability.get_settings",
        lambda: type("Settings", (), {"llm_timeout_seconds": 0.01})(),
    )

    run = asyncio.run(
        run_reliability_experiment(
            HangingLLM(),
            dataset,
            experiment_id="experiment-1",
            config=_config(dataset, repetitions=1),
        )
    )

    assert run.attempts[0].status == "FAILED"
    assert run.attempts[0].error_category == "TIMEOUT"
