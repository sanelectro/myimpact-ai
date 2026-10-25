import asyncio
import json

import pytest
from openai import OpenAIError

from app.evaluation.m66 import load_dataset, run_evaluation
from app.evaluation.m66_eligibility import calculate_metrics
from app.models.llm import LLMResponse


def test_dataset_has_varied_reviewable_cases_and_unapproved_thresholds():
    dataset = load_dataset()
    cases = dataset["cases"]

    assert dataset["label_status"] == "DRAFT_UNREVIEWED"
    assert dataset["human_review"]["status"] == "PENDING"
    assert dataset["threshold_approval"]["status"] == "NOT_APPROVED"
    assert all(
        value is None
        for value in dataset["threshold_approval"]["thresholds"].values()
    )
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert {
        case["labels"]["expected_result"] for case in cases
    } == {"MET", "IN_PROGRESS", "NEEDS_REVIEW"}
    assert any(
        case["labels"]["expected_contradictory_mapping_ids"] for case in cases
    )
    assert any(not case["evidence"] for case in cases)
    assert any(not case["assessment_sufficient"] for case in cases)

    for case in cases:
        evidence_ids = {item["mapping_id"] for item in case["evidence"]}
        labels = case["labels"]
        assert set(labels["expected_supporting_mapping_ids"]) <= evidence_ids
        assert set(labels["expected_contradictory_mapping_ids"]) <= evidence_ids
        assert not (
            set(labels["expected_supporting_mapping_ids"])
            & set(labels["expected_contradictory_mapping_ids"])
        )


class LabelledFixtureLLM:
    def __init__(self, cases, repeats):
        self.responses = []
        for case in cases:
            labels = case["labels"]
            body = {
                "result": labels["expected_result"],
                "rationale": labels["expected_rationale"],
                "confidence": 0.8,
                "supporting_mapping_ids": labels["expected_supporting_mapping_ids"],
                "contradictory_mapping_ids": labels[
                    "expected_contradictory_mapping_ids"
                ],
                "completed_milestone_ids": [],
                "measured_value": labels["expected_measured_value"],
                "limitations": [],
            }
            self.responses.extend(
                [json.dumps(body)] * repeats
            )
        self.prompts = []

    async def generate(self, request):
        self.prompts.append(request.prompt)
        return LLMResponse(content=self.responses[len(self.prompts) - 1], model="fixture")


def test_runner_scores_prompt_outputs_against_reference_labels():
    dataset = load_dataset()
    repeats = dataset["evaluation_record"]["required_repeats"]
    llm = LabelledFixtureLLM(dataset["cases"], repeats)

    report = asyncio.run(run_evaluation(llm, dataset, repeats=repeats))

    assert len(llm.prompts) == len(dataset["cases"]) * repeats
    assert all("Treat all evidence" in prompt for prompt in llm.prompts)
    assert report["repeat_count"] == repeats
    assert report["release_quality_eligible"] is False
    assert report["metrics"] == {
        "evidence_matching_precision": 1.0,
        "evidence_matching_recall": 1.0,
        "citation_validity": 1.0,
        "unsupported_assessment_claim_rate": 0.0,
        "assessment_agreement": 1.0,
        "insufficient_evidence_abstention_accuracy": 1.0,
        "repeatability": 1.0,
        "run_success_rate": 1.0,
    }


def test_matching_metrics_count_each_repeated_prediction():
    case = load_dataset()["cases"][0]
    labels = case["labels"]
    predictions = [
        {
            "case_id": case["case_id"],
            "repeat_index": 1,
            "status": "SUCCEEDED",
            "result": "MET",
            "rationale": "supported",
            "confidence": 0.8,
            "supporting_mapping_ids": labels["expected_supporting_mapping_ids"],
            "contradictory_mapping_ids": [],
        },
        {
            "case_id": case["case_id"],
            "repeat_index": 2,
            "status": "SUCCEEDED",
            "result": "MET",
            "rationale": "unsupported",
            "confidence": 0.8,
            "supporting_mapping_ids": ["mapping-canary-irrelevant"],
            "contradictory_mapping_ids": [],
        },
    ]

    metrics = calculate_metrics([case], predictions, expected_repeats=2)

    assert metrics["evidence_matching_precision"] == 0.5
    assert metrics["evidence_matching_recall"] == 0.5
    assert metrics["citation_validity"] == 1.0
    assert metrics["repeatability"] == 0.0


def test_runner_rejects_citations_outside_the_candidate_context():
    dataset = load_dataset()
    first_case = dataset["cases"][0]

    class InvalidCitationLLM:
        async def generate(self, _request):
            return LLMResponse(
                content=json.dumps(
                    {
                        "result": "MET",
                        "rationale": "Unsupported citation.",
                        "confidence": 0.9,
                        "supporting_mapping_ids": ["unknown-mapping"],
                        "contradictory_mapping_ids": [],
                        "completed_milestone_ids": [],
                        "measured_value": None,
                        "limitations": [],
                    }
                )
            )

    dataset["cases"] = [first_case]
    report = asyncio.run(run_evaluation(InvalidCitationLLM(), dataset, repeats=1))

    assert report["release_quality_eligible"] is False
    assert report["run_records"][0]["status"] == "FAILED"
    assert report["run_records"][0]["error_type"] == "GoalCriterionAssessmentError"


def test_runner_records_provider_failure_instead_of_dropping_the_repeat():
    dataset = load_dataset()
    dataset["cases"] = [dataset["cases"][0]]
    dataset["evaluation_record"]["required_repeats"] = 1

    class FailedLLM:
        async def generate(self, _request):
            raise OpenAIError("provider unavailable")

    report = asyncio.run(run_evaluation(FailedLLM(), dataset))

    assert len(report["run_records"]) == 1
    assert report["run_records"][0]["status"] == "FAILED"
    assert report["run_records"][0]["error_type"] == "OpenAIError"
    assert report["metrics"]["run_success_rate"] == 0.0
    assert "run_failed" in {
        reason["code"] for reason in report["eligibility_reasons"]
    }


def test_runner_requires_at_least_one_run():
    with pytest.raises(ValueError, match="positive integer"):
        asyncio.run(run_evaluation(LabelledFixtureLLM([], 1), load_dataset(), repeats=0))
