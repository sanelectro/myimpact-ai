import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAIError
from pydantic import ValidationError

from app.exceptions import GoalCriterionAssessmentError
from app.evaluation.m66_eligibility import (
    calculate_metrics,
    evaluate_release_eligibility,
)
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

DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "evaluation"
    / "m66_criterion_assessment.json"
)


def load_dataset(path: Path = DATASET_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as dataset_file:
        return json.load(dataset_file)


async def run_evaluation(
    llm_service: ILLMService,
    dataset: dict[str, Any],
    repeats: int | None = None,
) -> dict[str, Any]:
    evaluation_record = dataset.get("evaluation_record", {})
    declared_repeats = (
        evaluation_record.get("required_repeats")
        if isinstance(evaluation_record, dict)
        else None
    )
    if repeats is None:
        repeats = (
            declared_repeats
            if isinstance(declared_repeats, int)
            and not isinstance(declared_repeats, bool)
            else 3
        )
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        raise ValueError("repeats must be a positive integer")

    evaluated_at = datetime.now(UTC)
    expected_repeats = (
        declared_repeats
        if isinstance(declared_repeats, int)
        and not isinstance(declared_repeats, bool)
        and declared_repeats >= 1
        else repeats
    )
    run_records = []
    for case in dataset["cases"]:
        criterion = case["criterion"]
        definition = GoalCriterionDefinition.model_validate(criterion["definition"])
        mapping_ids = {item["mapping_id"] for item in case["evidence"]}
        prompt = build_criterion_assessment_prompt(
            criterion_id=criterion["id"],
            criterion_version_id=criterion["version_id"],
            criterion_version=criterion["version"],
            definition=definition,
            evidence_inputs=case["evidence"],
            retrieval_sufficient=case["retrieval_sufficient"],
        )
        for repeat_index in range(1, repeats + 1):
            record = {
                "case_id": case["case_id"],
                "repeat_index": repeat_index,
                "dataset_version": evaluation_record.get("dataset_version"),
                "prompt_version": ASSESSMENT_PROMPT_VERSION,
            }
            try:
                response = await llm_service.generate(
                    LLMRequest(
                        prompt=prompt,
                        response_format={"type": "json_object"},
                    )
                )
                proposal = GoalCriterionAssessmentProposal.model_validate_json(
                    normalize_assessment_response(response.content)
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
            except (
                OpenAIError,
                ValidationError,
                GoalCriterionAssessmentError,
            ) as exc:
                record.update(
                    {
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                    }
                )
            else:
                record.update(
                    {
                        "status": "SUCCEEDED",
                        "model_version": response.model,
                        **proposal.model_dump(mode="json"),
                        "result": assessed_result.value,
                    }
                )
            run_records.append(record)

    cases = dataset.get("cases", [])
    metrics = calculate_metrics(cases, run_records, expected_repeats)
    eligibility = evaluate_release_eligibility(
        dataset,
        run_records,
        evaluated_at=evaluated_at,
        requested_repeats=repeats,
    )
    predictions = {
        case["case_id"]: [
            record
            for record in run_records
            if record["case_id"] == case["case_id"]
        ]
        for case in cases
    }
    human_review = dataset.get("human_review", {})
    threshold_approval = dataset.get("threshold_approval", {})
    return {
        "dataset_id": dataset.get("dataset_id"),
        "human_review_status": (
            human_review.get("status") if isinstance(human_review, dict) else None
        ),
        "threshold_approval_status": (
            threshold_approval.get("status")
            if isinstance(threshold_approval, dict)
            else None
        ),
        "repeat_count": repeats,
        "required_repeat_count": expected_repeats,
        "evaluated_at": evaluated_at.isoformat(),
        "release_quality_eligible": eligibility["eligible"],
        "eligibility_reasons": eligibility["reasons"],
        "metrics": metrics,
        "run_records": run_records,
        "predictions": predictions,
    }
