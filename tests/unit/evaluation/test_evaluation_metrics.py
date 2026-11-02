from app.evaluation.assessment_evaluation import load_dataset
from app.evaluation.evaluation_eligibility import calculate_metric_results
from app.evaluation.evaluation_metrics import (
    METRIC_DEFINITIONS,
    MetricDirection,
    get_metric_definition,
)


def test_metric_catalogue_has_stable_complete_definitions():
    metric_ids = [definition.metric_id for definition in METRIC_DEFINITIONS]

    assert len(metric_ids) == len(set(metric_ids))
    assert set(metric_ids) == {
        "evidence_matching_precision",
        "evidence_matching_recall",
        "citation_validity",
        "assessment_agreement",
        "insufficient_evidence_abstention_accuracy",
        "repeatability",
        "run_success_rate",
        "unsupported_assessment_claim_rate",
    }
    assert (
        get_metric_definition("unsupported_assessment_claim_rate").direction
        == MetricDirection.LOWER_IS_BETTER
    )
    assert "outcome-level proxy" in get_metric_definition(
        "unsupported_assessment_claim_rate"
    ).limitations


def test_detailed_metric_results_preserve_numerators_and_denominators():
    dataset = load_dataset()
    case = dataset["cases"][0]
    labels = case["labels"]
    run_records = [
        {
            "case_id": case["case_id"],
            "repeat_index": 1,
            "status": "SUCCEEDED",
            "result": labels["expected_result"],
            "rationale": labels["expected_rationale"],
            "confidence": 0.8,
            "supporting_mapping_ids": labels["expected_supporting_mapping_ids"],
            "contradictory_mapping_ids": [],
        }
    ]

    results = calculate_metric_results([case], run_records, expected_repeats=1)

    assert results["evidence_matching_precision"].numerator == 1
    assert results["evidence_matching_precision"].denominator == 1
    assert results["evidence_matching_precision"].value == 1.0
    assert results["run_success_rate"].numerator == 1
    assert results["run_success_rate"].denominator == 1
    assert results["run_success_rate"].available is True


def test_zero_denominator_is_unavailable_not_zero():
    dataset = load_dataset()
    results = calculate_metric_results(
        [dataset["cases"][0]],
        [],
        expected_repeats=1,
    )

    precision = results["evidence_matching_precision"]
    assert precision.value is None
    assert precision.numerator == 0
    assert precision.denominator == 0
    assert precision.available is False
    assert precision.unavailable_reason
