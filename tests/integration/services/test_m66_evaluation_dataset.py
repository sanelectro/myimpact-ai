import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models.goal_criterion import GoalCriterionAssessmentDB
from app.evaluation.m66 import load_dataset
from app.models.goal import GoalScope
from app.models.llm import LLMResponse
from app.services.goal_assessment import GoalAssessmentService


@pytest.mark.integration
def test_production_assessment_path_handles_dataset_contradictions():
    case = next(
        item
        for item in load_dataset()["cases"]
        if item["case_id"] == "contradictory-release-outcomes"
    )
    labels = case["labels"]

    class AssessmentLLM:
        def __init__(self):
            self.prompt = ""

        async def generate(self, request):
            self.prompt = request.prompt
            return LLMResponse(
                content=json.dumps(
                    {
                        "result": labels["expected_result"],
                        "rationale": labels["expected_rationale"],
                        "confidence": 0.7,
                        "supporting_mapping_ids": labels[
                            "expected_supporting_mapping_ids"
                        ],
                        "contradictory_mapping_ids": labels[
                            "expected_contradictory_mapping_ids"
                        ],
                        "completed_milestone_ids": [],
                        "measured_value": None,
                        "limitations": ["The source reports conflict."],
                    }
                ),
                model="fixture-model",
            )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    GoalCriterionAssessmentDB.__table__.create(engine)
    llm_service = AssessmentLLM()

    with Session(engine) as session:
        assessment = asyncio.run(
            GoalAssessmentService(session, llm_service)._assess_criterion(
                run=SimpleNamespace(id="evaluation-run"),
                goal=SimpleNamespace(
                    id=case["goal"]["id"],
                    title=case["goal"]["title"],
                    description=case["goal"]["description"],
                    scope=GoalScope.PERSONAL,
                    start_date=None,
                    end_date=None,
                ),
                criterion=SimpleNamespace(id=case["criterion"]["id"]),
                version=SimpleNamespace(
                    id=case["criterion"]["version_id"],
                    version=case["criterion"]["version"],
                    definition=case["criterion"]["definition"],
                ),
                evidence_inputs=case["evidence"],
                retrieval_sufficient=case["retrieval_sufficient"],
            )
        )

    assert assessment.result.value == labels["expected_result"]
    assert assessment.progress_percentage is None
    assert {
        item.evidence_mapping_id: item.relationship_type
        for item in assessment.evidence
    } == {
        labels["expected_supporting_mapping_ids"][0]: "SUPPORTING",
        labels["expected_contradictory_mapping_ids"][0]: "CONTRADICTORY",
    }
    assert case["criterion"]["definition"]["description"] in llm_service.prompt
    assert all(item["content"] in llm_service.prompt for item in case["evidence"])
    engine.dispose()
