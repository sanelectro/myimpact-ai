from datetime import UTC, datetime
import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.reliability import (
    ReliabilityAttemptDB,
    ReliabilityComparisonDB,
    ReliabilityExperimentDB,
    ReliabilityReportDB,
)
from app.db.session import get_db
from app.evaluation.assessment_evaluation import load_dataset_by_id
from app.evaluation.reliability import (
    COMPARISON_VERSION,
    Attempt,
    ReliabilityExperimentConfig,
    run_reliability_experiment,
)
from app.services.llm.factory import create_llm_service

router = APIRouter(prefix="/reliability", tags=["m66-reliability"])
logger = logging.getLogger(__name__)


class ExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    dataset_id: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=200)
    case_selection: list[str] | None = Field(default=None, max_length=500)
    prompt_version: str = Field(min_length=1, max_length=200)
    model_identifier: str = Field(min_length=1, max_length=200)
    model_configuration: dict = Field(default_factory=dict)
    retrieval_configuration_version: str = Field(min_length=1, max_length=200)
    source_snapshot_id: str | None = Field(default=None, max_length=200)
    evaluation_code_version: str = Field(min_length=1, max_length=200)
    output_schema_version: str = Field(min_length=1, max_length=100)
    normalization_version: str = Field(min_length=1, max_length=100)
    repetitions_per_case: int = Field(default=3, ge=1, le=20)
    max_retries: int = Field(default=0, ge=0, le=3)
    execution_policy: dict = Field(
        default_factory=lambda: {"mode": "SEQUENTIAL", "max_concurrency": 1}
    )


class ExperimentResponse(BaseModel):
    id: str
    name: str
    dataset_id: str
    dataset_version: str
    case_selection: list[str]
    repetitions_per_case: int
    status: str
    planned_attempts: int
    completed_attempts: int
    failed_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str]


class AttemptResponse(BaseModel):
    id: str
    case_id: str
    sequence: int
    status: str
    schema_valid: bool
    raw_output: dict | None
    normalized_output: dict | None
    error_category: str | None
    error_detail: str | None


class ComparisonResponse(BaseModel):
    id: str
    case_id: str
    status: str
    metrics: dict
    exact_output_consistent: bool | None
    difference_categories: list[str]
    differences: list[dict]
    exclusion_reasons: list[str]


class ReportResponse(BaseModel):
    id: str
    report_version: str
    threshold_result: str
    metrics: dict
    coverage: dict
    divergent_case_ids: list[str]
    limitations: list[str]
    generated_at: datetime
    benchmark: dict | None = None


def _require_evaluation_access(user: AuthenticatedUser) -> None:
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )


def _config_from_experiment(
    experiment: ReliabilityExperimentDB,
) -> ReliabilityExperimentConfig:
    max_retries = experiment.execution_policy.get("max_retries", 2)
    return ReliabilityExperimentConfig(
        dataset_id=experiment.dataset_id,
        dataset_version=experiment.dataset_version,
        prompt_version=experiment.prompt_version,
        model_identifier=experiment.model_identifier,
        model_configuration=experiment.model_configuration,
        retrieval_configuration_version=experiment.retrieval_configuration_version,
        source_snapshot_id=experiment.source_snapshot_id,
        evaluation_code_version=experiment.evaluation_code_version,
        output_schema_version=experiment.output_schema_version,
        normalization_version=experiment.normalization_version,
        repetitions_per_case=experiment.repetitions_per_case,
        case_selection=tuple(experiment.case_selection),
        max_retries=max_retries,
    )


def _experiment_response(
    experiment: ReliabilityExperimentDB,
) -> ExperimentResponse:
    attempts = experiment.attempts
    return ExperimentResponse(
        id=experiment.id,
        name=experiment.name,
        dataset_id=experiment.dataset_id,
        dataset_version=experiment.dataset_version,
        case_selection=experiment.case_selection,
        repetitions_per_case=experiment.repetitions_per_case,
        status=experiment.status,
        planned_attempts=len(experiment.case_selection) * experiment.repetitions_per_case,
        completed_attempts=sum(attempt.status == "SUCCEEDED" for attempt in attempts),
        failed_attempts=sum(attempt.status == "FAILED" for attempt in attempts),
        created_at=experiment.created_at,
        started_at=experiment.started_at,
        finished_at=experiment.finished_at,
    )


def _get_experiment(
    db: Session,
    experiment_id: str,
    user: AuthenticatedUser,
) -> ReliabilityExperimentDB:
    experiment = db.get(ReliabilityExperimentDB, experiment_id)
    if experiment is None or (
        not user.is_platform_admin
        and experiment.created_by_user_id != user.user_id
    ):
        raise HTTPException(status_code=404, detail="Reliability experiment not found.")
    return experiment


@router.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    request: ExperimentCreateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ExperimentResponse:
    _require_evaluation_access(current_user)
    try:
        dataset = load_dataset_by_id(request.dataset_id, request.dataset_version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset version was not found.") from exc
    case_selection = tuple(request.case_selection or [
        case["case_id"] for case in dataset.get("cases", [])
    ])
    config = ReliabilityExperimentConfig(
        dataset_id=request.dataset_id,
        dataset_version=request.dataset_version,
        prompt_version=request.prompt_version,
        model_identifier=request.model_identifier,
        model_configuration=request.model_configuration,
        retrieval_configuration_version=request.retrieval_configuration_version,
        source_snapshot_id=request.source_snapshot_id,
        evaluation_code_version=request.evaluation_code_version,
        output_schema_version=request.output_schema_version,
        normalization_version=request.normalization_version,
        repetitions_per_case=request.repetitions_per_case,
        case_selection=case_selection,
        max_retries=request.max_retries,
    )
    errors = config.validate(dataset)
    if errors:
        raise HTTPException(status_code=422, detail=list(errors))
    now = datetime.now(UTC)
    experiment = ReliabilityExperimentDB(
        id=str(uuid4()),
        name=request.name.strip(),
        dataset_id=request.dataset_id,
        dataset_version=request.dataset_version,
        case_selection=list(case_selection),
        prompt_version=request.prompt_version,
        model_identifier=request.model_identifier,
        model_configuration=request.model_configuration,
        retrieval_configuration_version=request.retrieval_configuration_version,
        source_snapshot_id=request.source_snapshot_id,
        evaluation_code_version=request.evaluation_code_version,
        output_schema_version=request.output_schema_version,
        normalization_version=request.normalization_version,
        repetitions_per_case=request.repetitions_per_case,
        execution_policy={
            **request.execution_policy,
            "max_retries": request.max_retries,
        },
        status="DRAFT",
        created_by_user_id=current_user.user_id,
        created_at=now,
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return _experiment_response(experiment)


@router.get("/experiments", response_model=list[ExperimentResponse])
def list_experiments(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ExperimentResponse]:
    _require_evaluation_access(current_user)
    experiments = db.scalars(
        select(ReliabilityExperimentDB)
        .order_by(ReliabilityExperimentDB.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [_experiment_response(experiment) for experiment in experiments]


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(
    experiment_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ExperimentResponse:
    _require_evaluation_access(current_user)
    return _experiment_response(_get_experiment(db, experiment_id, current_user))


@router.post(
    "/experiments/{experiment_id}/validate",
    response_model=ValidationResponse,
)
def validate_experiment(
    experiment_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ValidationResponse:
    _require_evaluation_access(current_user)
    experiment = _get_experiment(db, experiment_id, current_user)
    try:
        dataset = load_dataset_by_id(experiment.dataset_id, experiment.dataset_version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset version was not found.") from exc
    errors = _config_from_experiment(experiment).validate(dataset)
    return ValidationResponse(valid=not errors, errors=list(errors))


@router.post(
    "/experiments/{experiment_id}/start",
    response_model=ExperimentResponse,
)
async def start_experiment(
    experiment_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ExperimentResponse:
    _require_evaluation_access(current_user)
    experiment = _get_experiment(db, experiment_id, current_user)
    if experiment.status == "COMPLETED":
        return _experiment_response(experiment)
    if experiment.status == "RUNNING":
        raise HTTPException(status_code=409, detail="Experiment is already running.")
    try:
        dataset = load_dataset_by_id(experiment.dataset_id, experiment.dataset_version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset version was not found.") from exc
    config = _config_from_experiment(experiment)
    errors = config.validate(dataset)
    if errors:
        raise HTTPException(status_code=422, detail=list(errors))
    db.execute(
        delete(ReliabilityAttemptDB).where(
            ReliabilityAttemptDB.experiment_id == experiment.id
        )
    )
    db.execute(
        delete(ReliabilityComparisonDB).where(
            ReliabilityComparisonDB.experiment_id == experiment.id
        )
    )
    db.execute(
        delete(ReliabilityReportDB).where(
            ReliabilityReportDB.experiment_id == experiment.id
        )
    )
    experiment.status = "RUNNING"
    experiment.started_at = datetime.now(UTC)
    db.commit()
    async def persist_attempt(attempt: Attempt) -> None:
        db.add(
            ReliabilityAttemptDB(
                id=attempt.attempt_id,
                experiment_id=experiment.id,
                case_id=attempt.case_id,
                sequence=attempt.sequence,
                dataset_version=config.dataset_version,
                prompt_version=config.prompt_version,
                model_identifier=attempt.model_identifier or config.model_identifier,
                retrieval_configuration_version=config.retrieval_configuration_version,
                source_snapshot_id=attempt.source_snapshot_id,
                input_fingerprint=attempt.input_fingerprint or "",
                raw_output=dict(attempt.raw_output) if attempt.raw_output else None,
                normalized_output=(
                    attempt.normalized_output.as_dict()
                    if attempt.normalized_output
                    else None
                ),
                schema_valid=attempt.schema_valid,
                status=attempt.status,
                error_category=attempt.error_category,
                error_detail=attempt.error_detail,
                started_at=experiment.started_at,
                finished_at=datetime.now(UTC),
            )
        )
        db.commit()
        logger.info(
            "Persisted reliability attempt experiment_id=%s case_id=%s sequence=%s status=%s",
            experiment.id,
            attempt.case_id,
            attempt.sequence,
            attempt.status,
        )

    try:
        run = await run_reliability_experiment(
            create_llm_service(),
            dataset,
            experiment_id=experiment.id,
            config=config,
            on_attempt=persist_attempt,
        )
    except Exception:
        db.rollback()
        experiment.status = "FAILED"
        experiment.finished_at = datetime.now(UTC)
        db.commit()
        logger.exception("Reliability experiment failed experiment_id=%s", experiment.id)
        raise
    for comparison in run.report.comparisons:
        db.add(
            ReliabilityComparisonDB(
                id=str(uuid4()),
                experiment_id=experiment.id,
                case_id=comparison.case_id,
                attempt_ids=list(comparison.attempt_ids),
                status=comparison.status.value,
                metrics={
                    "label": comparison.label_metric.__dict__,
                    "evidence": comparison.evidence_metric.__dict__,
                    "citation": comparison.citation_metric.__dict__,
                    "abstention": comparison.abstention_metric.__dict__,
                },
                exact_output_consistent=comparison.exact_output_consistent,
                difference_categories=[
                    category.value for category in comparison.difference_categories
                ],
                differences=list(comparison.differences),
                exclusion_reasons=list(comparison.exclusion_reasons),
                comparison_version=COMPARISON_VERSION,
                created_at=datetime.now(UTC),
            )
        )
    report = run.report
    db.add(
        ReliabilityReportDB(
            id=str(uuid4()),
            experiment_id=experiment.id,
            report_version=report.report_version,
            metric_definition_versions={"comparison": report.comparison_version},
            threshold_result=report.threshold_result.value,
            metrics={
                key: value.__dict__ for key, value in report.metrics.items()
            },
            coverage={
                "planned_attempts": report.planned_attempts,
                "completed_attempts": report.completed_attempts,
                "failed_attempts": report.failed_attempts,
                "invalid_attempts": report.invalid_attempts,
                "incomplete_cases": report.incomplete_cases,
            },
            divergent_case_ids=[
                comparison.case_id
                for comparison in report.comparisons
                if comparison.differences
            ],
            limitations=list(report.limitations),
            generated_at=datetime.now(UTC),
        )
    )
    experiment.status = "COMPLETED"
    experiment.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(experiment)
    return _experiment_response(experiment)


@router.get(
    "/experiments/{experiment_id}/attempts",
    response_model=list[AttemptResponse],
)
def list_attempts(
    experiment_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    case_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AttemptResponse]:
    _require_evaluation_access(current_user)
    experiment = _get_experiment(db, experiment_id, current_user)
    query = select(ReliabilityAttemptDB).where(
        ReliabilityAttemptDB.experiment_id == experiment.id
    )
    if case_id:
        query = query.where(ReliabilityAttemptDB.case_id == case_id)
    attempts = db.scalars(
        query.order_by(
            ReliabilityAttemptDB.case_id,
            ReliabilityAttemptDB.sequence,
        ).offset(offset).limit(limit)
    ).all()
    return [AttemptResponse.model_validate(attempt, from_attributes=True) for attempt in attempts]


@router.get(
    "/experiments/{experiment_id}/comparisons",
    response_model=list[ComparisonResponse],
)
def list_comparisons(
    experiment_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ComparisonResponse]:
    _require_evaluation_access(current_user)
    experiment = _get_experiment(db, experiment_id, current_user)
    comparisons = db.scalars(
        select(ReliabilityComparisonDB)
        .where(ReliabilityComparisonDB.experiment_id == experiment.id)
        .order_by(ReliabilityComparisonDB.case_id)
    ).all()
    return [
        ComparisonResponse.model_validate(comparison, from_attributes=True)
        for comparison in comparisons
    ]


@router.get(
    "/experiments/{experiment_id}/report",
    response_model=ReportResponse,
)
def get_report(
    experiment_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportResponse:
    _require_evaluation_access(current_user)
    experiment = _get_experiment(db, experiment_id, current_user)
    report = db.scalar(
        select(ReliabilityReportDB)
        .where(ReliabilityReportDB.experiment_id == experiment.id)
        .order_by(ReliabilityReportDB.generated_at.desc())
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Reliability report not found.")
    response = ReportResponse.model_validate(report, from_attributes=True)
    try:
        dataset = load_dataset_by_id(experiment.dataset_id, experiment.dataset_version)
    except FileNotFoundError:
        return response
    cases = dataset.get("cases", [])
    categories = sorted(
        {
            case["category"]
            for case in cases
            if isinstance(case, dict) and isinstance(case.get("category"), str)
        }
    )
    category_by_case = {
        case["case_id"]: case.get("category", "uncategorized")
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    comparisons = db.scalars(
        select(ReliabilityComparisonDB).where(
            ReliabilityComparisonDB.experiment_id == experiment.id
        )
    ).all()
    category_breakdown: dict[str, dict[str, int]] = {}
    for comparison in comparisons:
        category = category_by_case.get(comparison.case_id, "uncategorized")
        summary = category_breakdown.setdefault(
            category,
            {"cases": 0, "complete": 0, "divergent": 0},
        )
        summary["cases"] += 1
        if comparison.status == "COMPLETE":
            summary["complete"] += 1
        if comparison.differences:
            summary["divergent"] += 1
    expected_by_case = {
        case["case_id"]: case.get("labels", {}).get("expected_result")
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    attempts = db.scalars(
        select(ReliabilityAttemptDB).where(
            ReliabilityAttemptDB.experiment_id == experiment.id
        )
    ).all()
    successful_attempts = [
        attempt
        for attempt in attempts
        if attempt.status == "SUCCEEDED"
        and attempt.schema_valid
        and isinstance(attempt.normalized_output, dict)
    ]
    correctness_numerator = sum(
        attempt.normalized_output.get("result")
        == expected_by_case.get(attempt.case_id)
        for attempt in successful_attempts
    )
    correctness_denominator = len(attempts)
    robustness_attempts = [
        attempt
        for attempt in successful_attempts
        if not next(
            (
                case.get("assessment_sufficient", True)
                for case in cases
                if isinstance(case, dict)
                and case.get("case_id") == attempt.case_id
            ),
            True,
        )
    ]
    robustness_numerator = sum(
        attempt.normalized_output.get("result") == "NEEDS_REVIEW"
        for attempt in robustness_attempts
    )
    return response.model_copy(
        update={
            "benchmark": {
                "dataset_id": dataset.get("dataset_id"),
                "dataset_version": dataset.get("evaluation_record", {}).get(
                    "dataset_version"
                ),
                "label_status": dataset.get("label_status"),
                "human_review_status": dataset.get("human_review", {}).get("status"),
                "threshold_approval_status": dataset.get(
                    "threshold_approval", {}
                ).get("status"),
                "case_count": len(cases),
                "categories": categories,
                "category_breakdown": category_breakdown,
                "metrics": {
                    "correctness": {
                        "value": None,
                        "numerator": correctness_numerator,
                        "denominator": correctness_denominator,
                        "status": "NOT_EVALUABLE",
                        "reason": "Provisional labels require human approval before correctness is evaluated.",
                    },
                    "robustness_abstention": {
                        "value": None,
                        "numerator": robustness_numerator,
                        "denominator": len(robustness_attempts),
                        "status": "NOT_EVALUABLE",
                        "reason": "Robustness cases remain provisional until dual adjudication is complete.",
                    },
                },
                "baseline_dataset_id": dataset.get("benchmark_governance", {}).get(
                    "baseline_dataset_id"
                ),
                "minimum_sample_policy": dataset.get(
                    "benchmark_governance", {}
                ).get("minimum_sample_policy"),
            }
        }
    )
