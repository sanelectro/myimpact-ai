import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, get_current_user
from app.db.base import Base
from app.db.models.reliability import (
    AIModelDB,
    ReliabilityAttemptDB,
    ReliabilityComparisonDB,
    ReliabilityExperimentDB,
    ReliabilityReportDB,
)
from app.db.session import get_db
from app.evaluation.assessment_evaluation import load_dataset
from app.main import app
from app.services.goal_assessment import ASSESSMENT_PROMPT_VERSION
from app.models.llm import LLMResponse


def test_admin_can_create_validate_and_list_reliability_experiment():
    dataset = load_dataset()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        AIModelDB.__table__,
        ReliabilityExperimentDB.__table__,
        ReliabilityAttemptDB.__table__,
        ReliabilityComparisonDB.__table__,
        ReliabilityReportDB.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "admin-1",
        "admin@example.com",
        "Platform Admin",
        {"myimpact-ai"},
        is_platform_admin=True,
    )
    client = TestClient(app)
    payload = {
        "name": "Repeatability smoke test",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["evaluation_record"]["dataset_version"],
        "case_selection": [dataset["cases"][0]["case_id"]],
        "prompt_version": ASSESSMENT_PROMPT_VERSION,
        "model_identifier": "fixture-model",
        "model_configuration": {"temperature": 0},
        "retrieval_configuration_version": "retrieval-v1",
        "source_snapshot_id": "snapshot-v1",
        "evaluation_code_version": "test-code",
        "output_schema_version": "assessment-v1",
        "normalization_version": "m66-reliability-normalization-v1",
        "repetitions_per_case": 3,
    }
    try:
        created = client.post("/api/v1/reliability/experiments", json=payload)
        assert created.status_code == 201
        experiment_id = created.json()["id"]

        validation = client.post(
            f"/api/v1/reliability/experiments/{experiment_id}/validate"
        )
        assert validation.status_code == 200
        assert validation.json() == {"valid": True, "errors": []}

        listed = client.get("/api/v1/reliability/experiments")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == experiment_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()


def test_non_admin_cannot_create_reliability_experiment():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "user-1",
        "user@example.com",
        "Software Engineer",
        {"myimpact-ai"},
    )
    try:
        response = TestClient(app).post(
            "/api/v1/reliability/experiments",
            json={
                "name": "not allowed",
                "dataset_id": "dataset",
                "dataset_version": "version",
                "prompt_version": "prompt",
                "model_identifier": "model",
                "retrieval_configuration_version": "retrieval",
                "evaluation_code_version": "code",
                "output_schema_version": "schema",
                "normalization_version": "normalization",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403


def test_admin_can_start_experiment_and_retrieve_persisted_report(monkeypatch):
    dataset = load_dataset()
    case = dataset["cases"][0]
    labels = case["labels"]
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        AIModelDB.__table__,
        ReliabilityExperimentDB.__table__,
        ReliabilityAttemptDB.__table__,
        ReliabilityComparisonDB.__table__,
        ReliabilityReportDB.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)

    class FixtureLLM:
        async def generate(self, _request):
            return LLMResponse(
                content=json.dumps(
                    {
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
                ),
                model="fixture-model",
            )

    monkeypatch.setattr(
        "app.api.v1.reliability.create_llm_service",
        lambda: FixtureLLM(),
    )

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "admin-1",
        "admin@example.com",
        "Platform Admin",
        {"myimpact-ai"},
        is_platform_admin=True,
    )
    payload = {
        "name": "Start smoke test",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["evaluation_record"]["dataset_version"],
        "case_selection": [case["case_id"]],
        "prompt_version": ASSESSMENT_PROMPT_VERSION,
        "model_identifier": "fixture-model",
        "model_configuration": {"temperature": 0},
        "retrieval_configuration_version": "retrieval-v1",
        "evaluation_code_version": "test-code",
        "output_schema_version": "assessment-v1",
        "normalization_version": "m66-reliability-normalization-v1",
        "repetitions_per_case": 3,
    }
    client = TestClient(app)
    try:
        created = client.post("/api/v1/reliability/experiments", json=payload)
        experiment_id = created.json()["id"]
        started = client.post(
            f"/api/v1/reliability/experiments/{experiment_id}/start"
        )
        assert started.status_code == 200
        assert started.json()["status"] == "COMPLETED"

        attempts = client.get(
            f"/api/v1/reliability/experiments/{experiment_id}/attempts"
        )
        assert attempts.status_code == 200
        assert len(attempts.json()) == 3

        report = client.get(
            f"/api/v1/reliability/experiments/{experiment_id}/report"
        )
        assert report.status_code == 200
        assert report.json()["coverage"]["planned_attempts"] == 3
        assert report.json()["threshold_result"] == "NOT_EVALUABLE"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()
