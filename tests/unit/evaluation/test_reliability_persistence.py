from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.reliability import (
    ReliabilityAttemptDB,
    ReliabilityComparisonDB,
    ReliabilityExperimentDB,
    ReliabilityReportDB,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        ReliabilityExperimentDB.__table__,
        ReliabilityAttemptDB.__table__,
        ReliabilityComparisonDB.__table__,
        ReliabilityReportDB.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _experiment():
    return ReliabilityExperimentDB(
        id="experiment-1",
        name="Repeatability smoke test",
        dataset_id="dataset-1",
        dataset_version="dataset-v1",
        case_selection=["case-1"],
        prompt_version="prompt-v1",
        model_identifier="fixture-model",
        model_configuration={"temperature": 0},
        retrieval_configuration_version="retrieval-v1",
        source_snapshot_id="snapshot-1",
        evaluation_code_version="code-v1",
        output_schema_version="schema-v1",
        normalization_version="normalization-v1",
        repetitions_per_case=3,
        execution_policy={"mode": "SEQUENTIAL", "max_concurrency": 1},
        status="DRAFT",
        created_by_user_id="user-1",
        created_at=datetime.now(UTC),
    )


def test_attempt_sequence_is_unique_per_case(session):
    session.add(_experiment())
    session.commit()
    common = {
        "experiment_id": "experiment-1",
        "case_id": "case-1",
        "sequence": 1,
        "dataset_version": "dataset-v1",
        "prompt_version": "prompt-v1",
        "model_identifier": "fixture-model",
        "retrieval_configuration_version": "retrieval-v1",
        "input_fingerprint": "input-v1",
        "schema_valid": True,
        "status": "SUCCEEDED",
        "started_at": datetime.now(UTC),
    }
    session.add(ReliabilityAttemptDB(id="attempt-1", **common))
    session.commit()
    session.add(ReliabilityAttemptDB(id="attempt-2", **common))

    with pytest.raises(IntegrityError):
        session.commit()


def test_report_and_comparison_remain_available_as_historical_records(session):
    session.add(_experiment())
    session.add(
        ReliabilityComparisonDB(
            id="comparison-1",
            experiment_id="experiment-1",
            case_id="case-1",
            attempt_ids=["attempt-1", "attempt-2", "attempt-3"],
            status="COMPLETE",
            metrics={"label_consistency": {"value": 1.0}},
            exact_output_consistent=True,
            difference_categories=[],
            differences=[],
            exclusion_reasons=[],
            comparison_version="comparison-v1",
            created_at=datetime.now(UTC),
        )
    )
    session.add(
        ReliabilityReportDB(
            id="report-1",
            experiment_id="experiment-1",
            report_version="report-v1",
            metric_definition_versions={"label_consistency": "comparison-v1"},
            threshold_set_id=None,
            threshold_set_version=None,
            threshold_result="NOT_EVALUABLE",
            metrics={"label_consistency": {"value": 1.0}},
            coverage={"planned_attempts": 3},
            divergent_case_ids=[],
            limitations=["Consistency is not correctness."],
            generated_at=datetime.now(UTC),
        )
    )
    session.commit()

    report = session.get(ReliabilityReportDB, "report-1")
    comparison = session.get(ReliabilityComparisonDB, "comparison-1")
    assert report is not None
    assert report.metrics["label_consistency"]["value"] == 1.0
    assert comparison is not None
    assert comparison.exact_output_consistent is True
