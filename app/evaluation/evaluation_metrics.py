from dataclasses import dataclass
from enum import Enum


class MetricUnit(str, Enum):
    RATIO = "RATIO"


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    name: str
    description: str
    definition_version: str
    unit: MetricUnit
    direction: MetricDirection
    numerator_definition: str
    denominator_definition: str
    inclusion_rules: str
    exclusion_rules: str
    zero_denominator_behavior: str
    required_inputs: tuple[str, ...]
    limitations: str
    calculation_version: str
    active: bool = True


@dataclass(frozen=True)
class MetricResult:
    metric_id: str
    definition_version: str
    calculation_version: str
    value: float | None
    numerator: int
    denominator: int
    available: bool
    unavailable_reason: str | None = None


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        metric_id="evidence_matching_precision",
        name="Evidence matching precision",
        description="The proportion of selected evidence items that match the reviewed relevant reference set.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.HIGHER_IS_BETTER,
        numerator_definition="Selected supporting or contradictory mapping IDs that match the reviewed relevant reference set.",
        denominator_definition="All supporting and contradictory mapping IDs selected by the assessment.",
        inclusion_rules="One evidence mapping ID counts as one selected item; supporting and contradictory relationships are distinct.",
        exclusion_rules="Invalid or failed assessment runs are excluded.",
        zero_denominator_behavior="Unavailable when no evidence item is selected.",
        required_inputs=("run_records", "reviewed_case_reference_evidence"),
        limitations="Precision does not measure whether all relevant evidence was retrieved.",
        calculation_version="m66-metric-calculation-v1",
    ),
    MetricDefinition(
        metric_id="evidence_matching_recall",
        name="Evidence matching recall",
        description="The proportion of reviewed relevant evidence items selected by the assessment.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.HIGHER_IS_BETTER,
        numerator_definition="Selected evidence mapping IDs that match the reviewed relevant reference set.",
        denominator_definition="All reviewed relevant evidence mapping IDs in the reference set.",
        inclusion_rules="Each reviewed relevant mapping ID counts once per repeat.",
        exclusion_rules="Invalid or failed assessment runs are excluded from the numerator.",
        zero_denominator_behavior="Unavailable when the reviewed reference set contains no relevant evidence.",
        required_inputs=("run_records", "reviewed_case_reference_evidence"),
        limitations="Recall depends on the completeness of the reviewed reference set and retrieval scope.",
        calculation_version="m66-metric-calculation-v1",
    ),
    MetricDefinition(
        metric_id="citation_validity",
        name="Citation validity",
        description="The proportion of supplied citation mapping IDs that resolve to candidate evidence in the case context.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.HIGHER_IS_BETTER,
        numerator_definition="Supplied citation mapping IDs present in the candidate evidence context.",
        denominator_definition="All supporting and contradictory citation mapping IDs supplied by the assessment.",
        inclusion_rules="Each supplied citation mapping ID counts once.",
        exclusion_rules="Invalid or failed assessment runs are excluded.",
        zero_denominator_behavior="Unavailable when no citations are supplied.",
        required_inputs=("run_records", "candidate_evidence"),
        limitations="A resolving citation does not prove claim-level factual support or authorization accessibility.",
        calculation_version="m66-metric-calculation-v1",
    ),
    MetricDefinition(
        metric_id="assessment_agreement",
        name="Assessment agreement",
        description="The proportion of successful assessment slots whose result matches the reviewed expected outcome.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.HIGHER_IS_BETTER,
        numerator_definition="Successful case/repeat slots whose assessment result equals the reviewed expected result.",
        denominator_definition="All declared case/repeat slots.",
        inclusion_rules="Every declared case/repeat slot is included in the denominator.",
        exclusion_rules="None from the denominator; failed or missing slots do not count as agreement.",
        zero_denominator_behavior="Unavailable when no case/repeat slots are declared.",
        required_inputs=("run_records", "reviewed_case_expected_results", "required_repeats"),
        limitations="Agreement depends on the quality and coverage of reviewed expected outcomes.",
        calculation_version="m66-metric-calculation-v1",
    ),
    MetricDefinition(
        metric_id="insufficient_evidence_abstention_accuracy",
        name="Insufficient-evidence abstention accuracy",
        description="The proportion of abstention-evaluation slots that correctly return NEEDS_REVIEW.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.HIGHER_IS_BETTER,
        numerator_definition="Insufficient-evidence slots whose result is NEEDS_REVIEW.",
        denominator_definition="Insufficient-evidence slots with a valid or invalid run outcome.",
        inclusion_rules="Cases marked assessment_sufficient=false are evaluated.",
        exclusion_rules="Sufficient-evidence cases are excluded.",
        zero_denominator_behavior="Unavailable when no insufficient-evidence case is present.",
        required_inputs=("run_records", "reviewed_case_sufficiency_labels"),
        limitations="This measures outcome abstention, not whether every rationale claim is supported.",
        calculation_version="m66-metric-calculation-v1",
    ),
    MetricDefinition(
        metric_id="repeatability",
        name="Assessment repeatability",
        description="The proportion of cases with one valid, identical result and citation signature across all repeats.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.HIGHER_IS_BETTER,
        numerator_definition="Cases whose every declared repeat succeeds with the same result and citation signature.",
        denominator_definition="All evaluation cases.",
        inclusion_rules="Result, supporting IDs, and contradictory IDs form the repeat signature.",
        exclusion_rules="Cases with missing, duplicate, failed, or invalid repeat slots are not repeatable.",
        zero_denominator_behavior="Unavailable when no cases are declared.",
        required_inputs=("run_records", "required_repeats"),
        limitations="Repeatability does not establish correctness.",
        calculation_version="m66-metric-calculation-v1",
    ),
    MetricDefinition(
        metric_id="run_success_rate",
        name="Run success rate",
        description="The proportion of declared case/repeat slots that complete with a valid assessment.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.HIGHER_IS_BETTER,
        numerator_definition="Case/repeat slots with SUCCEEDED status and valid structured output.",
        denominator_definition="All declared case/repeat slots.",
        inclusion_rules="Every declared case/repeat slot is included.",
        exclusion_rules="None from the denominator.",
        zero_denominator_behavior="Unavailable when no case/repeat slots are declared.",
        required_inputs=("run_records", "required_repeats"),
        limitations="A successful run may still produce an incorrect assessment.",
        calculation_version="m66-metric-calculation-v1",
    ),
    MetricDefinition(
        metric_id="unsupported_assessment_claim_rate",
        name="Unsupported assessment claim rate",
        description="The outcome-level rate of achievement predictions lacking reviewed support; this is not claim-level factuality.",
        definition_version="m66-metrics-v1",
        unit=MetricUnit.RATIO,
        direction=MetricDirection.LOWER_IS_BETTER,
        numerator_definition="Achievement predictions that lack an expected achievement outcome or reviewed supporting mapping overlap.",
        denominator_definition="Successful predictions with an IN_PROGRESS or MET result.",
        inclusion_rules="Only successful achievement-result predictions are evaluated.",
        exclusion_rules="Non-achievement results and failed/invalid runs are excluded.",
        zero_denominator_behavior="Unavailable when no successful achievement prediction exists.",
        required_inputs=("run_records", "reviewed_case_expected_results", "reviewed_case_supporting_evidence"),
        limitations="This is an outcome-level proxy and does not verify each generated factual claim.",
        calculation_version="m66-metric-calculation-v1",
    ),
)

METRIC_DEFINITIONS_BY_ID = {definition.metric_id: definition for definition in METRIC_DEFINITIONS}


def get_metric_definition(metric_id: str) -> MetricDefinition:
    try:
        return METRIC_DEFINITIONS_BY_ID[metric_id]
    except KeyError as exc:
        raise KeyError(f"Unknown M6.6 metric: {metric_id}") from exc
