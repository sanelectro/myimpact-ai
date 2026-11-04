from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.human_review import (
    ReviewAssignmentDB,
    ReviewAuditEventDB,
    ReviewBatchDB,
    ReviewCaseDB,
    ReviewDB,
)
from app.db.models.reliability import ReliabilityAttemptDB, ReliabilityExperimentDB
from app.db.session import get_db
from app.evaluation.assessment_evaluation import DATASET_PATHS, load_dataset_by_id
from app.models.human_review import M66CaseReviewStatus, M66DatasetReviewStatus
from app.services.human_review import (
    M66ReviewError,
    create_review_batch,
    get_case_for_reviewer,
    submit_adjudication,
    submit_review,
)

router = APIRouter(prefix="/human-review", tags=["human-review"])


class ReviewBatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=200)
    case_ids: list[str] = Field(min_length=1, max_length=500)
    assignments: dict[str, list[str]]
    review_mode: str = Field(default="DUAL_ADJUDICATED", pattern="^(SINGLE_REVIEWER|DUAL_ADJUDICATED)$")


class ReviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=10000)


class AdjudicationSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_label: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=10000)


class ReviewBatchResponse(BaseModel):
    id: str
    dataset_id: str
    dataset_version: str
    review_mode: str
    status: M66DatasetReviewStatus
    expected_case_count: int
    started_at: str
    completed_at: str | None


class ReviewCaseSummary(BaseModel):
    case_id: str
    category: str | None = None
    status: M66CaseReviewStatus
    submitted_by_current_user: bool


class ReviewResponse(BaseModel):
    id: str
    case_id: str
    reviewer_user_id: str
    label: str
    rationale: str
    submitted_at: str


class ReviewProgressResponse(BaseModel):
    batch: ReviewBatchResponse
    total_cases: int
    awaiting_first_review: int
    awaiting_second_review: int
    reviewed: int
    agreed: int
    disagreement: int
    adjudicated: int
    category_progress: list[dict]
    evaluation: dict


def _require_platform_admin(current_user: AuthenticatedUser) -> None:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )


def _require_reviewer_or_admin(current_user: AuthenticatedUser) -> None:
    if not current_user.is_reviewer and not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dedicated evaluation reviewer access is required.",
        )


def _batch_response(batch: ReviewBatchDB) -> ReviewBatchResponse:
    return ReviewBatchResponse(
        id=batch.id,
        dataset_id=batch.dataset_id,
        dataset_version=batch.dataset_version,
        review_mode=batch.review_mode,
        status=batch.status,
        expected_case_count=batch.expected_case_count,
        started_at=batch.started_at.isoformat(),
        completed_at=batch.completed_at.isoformat() if batch.completed_at else None,
    )


def _get_batch(db: Session, batch_id: str) -> ReviewBatchDB:
    batch = db.get(ReviewBatchDB, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Review batch was not found.")
    return batch


def _latest_ai_assessment(
    db: Session,
    *,
    dataset_id: str,
    dataset_version: str,
    case_id: str,
) -> dict[str, object] | None:
    attempt = db.scalar(
        select(ReliabilityAttemptDB)
        .join(
            ReliabilityExperimentDB,
            ReliabilityExperimentDB.id == ReliabilityAttemptDB.experiment_id,
        )
        .where(
            ReliabilityExperimentDB.dataset_id == dataset_id,
            ReliabilityExperimentDB.dataset_version == dataset_version,
            ReliabilityAttemptDB.case_id == case_id,
            ReliabilityAttemptDB.status == "SUCCEEDED",
            ReliabilityAttemptDB.normalized_output.is_not(None),
        )
        .order_by(ReliabilityAttemptDB.finished_at.desc())
    )
    if attempt is None or attempt.normalized_output is None:
        return None
    raw_output = attempt.raw_output or {}
    normalized_output = attempt.normalized_output
    return {
        "attempt_id": attempt.id,
        "model_identifier": attempt.model_identifier,
        "assessment_label": normalized_output.get("assessment_label"),
        "rationale": raw_output.get("rationale"),
        "confidence": raw_output.get("confidence"),
        "supporting_mapping_ids": normalized_output.get("supporting_evidence_ids", []),
        "contradictory_mapping_ids": normalized_output.get("contradictory_evidence_ids", []),
        "limitations": raw_output.get("limitations", []),
        "abstained": normalized_output.get("abstained"),
        "structured_status": normalized_output.get("structured_status"),
    }


@router.post(
    "/batches",
    response_model=ReviewBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_batch(
    request: ReviewBatchCreateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewBatchResponse:
    _require_platform_admin(current_user)
    if request.dataset_id not in DATASET_PATHS:
        raise HTTPException(status_code=404, detail="Dataset was not found.")
    try:
        dataset = load_dataset_by_id(request.dataset_id, request.dataset_version)
    except FileNotFoundError:
        raise HTTPException(status_code=409, detail="Dataset version is not available.")
    available_case_ids = {case["case_id"] for case in dataset.get("cases", [])}
    if not set(request.case_ids) <= available_case_ids:
        raise HTTPException(status_code=422, detail="A requested case is not in the dataset.")
    try:
        batch = create_review_batch(
            db,
            dataset_id=request.dataset_id,
            dataset_version=request.dataset_version,
            case_ids=request.case_ids,
            started_by_user_id=current_user.user_id,
            assignments=request.assignments,
            review_mode=request.review_mode,
        )
    except M66ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _batch_response(batch)


@router.get("/batches", response_model=list[ReviewBatchResponse])
def list_review_batches(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ReviewBatchResponse]:
    _require_reviewer_or_admin(current_user)
    query = select(ReviewBatchDB).order_by(ReviewBatchDB.started_at.desc())
    if not current_user.is_platform_admin:
        query = query.where(
            ReviewBatchDB.cases.any(
                ReviewCaseDB.assignments.any(
                    ReviewAssignmentDB.reviewer_user_id == current_user.user_id
                )
            )
        )
    batches = db.scalars(query).all()
    return [_batch_response(batch) for batch in batches]


@router.get("/batches/{batch_id}/queue", response_model=list[ReviewCaseSummary])
def reviewer_queue(
    batch_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ReviewCaseSummary]:
    _require_reviewer_or_admin(current_user)
    batch = _get_batch(db, batch_id)
    dataset = load_dataset_by_id(batch.dataset_id, batch.dataset_version)
    categories = {
        case["case_id"]: case.get("category")
        for case in dataset.get("cases", [])
    }
    cases = db.scalars(
        select(ReviewCaseDB)
        .where(
            ReviewCaseDB.batch_id == batch.id,
            ReviewCaseDB.assignments.any(
                ReviewAssignmentDB.reviewer_user_id == current_user.user_id
            ),
        )
    ).all()
    return [
        ReviewCaseSummary(
            case_id=case.case_id,
            category=categories.get(case.case_id),
            status=case.status,
            submitted_by_current_user=any(
                review.reviewer_user_id == current_user.user_id
                for review in case.reviews
            ),
        )
        for case in cases
    ]


@router.get("/batches/{batch_id}/cases/{case_id}")
def get_review_case(
    batch_id: str,
    case_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _require_reviewer_or_admin(current_user)
    batch = _get_batch(db, batch_id)
    dataset = load_dataset_by_id(batch.dataset_id, batch.dataset_version)
    case_context = next(
        (case for case in dataset.get("cases", []) if case["case_id"] == case_id),
        None,
    )
    if case_context is None:
        raise HTTPException(status_code=404, detail="Evaluation case was not found.")
    try:
        view = get_case_for_reviewer(
            db,
            batch_id=batch_id,
            case_id=case_id,
            reviewer_user_id=current_user.user_id,
        )
    except M66ReviewError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    ai_assessment = None
    if view["own_review"] is not None:
        ai_assessment = _latest_ai_assessment(
            db,
            dataset_id=view["case"].batch.dataset_id,
            dataset_version=view["case"].batch.dataset_version,
            case_id=view["case"].case_id,
        )
    return {
        "case": case_context,
        "status": view["case"].status,
        "own_review": _review_response(view["own_review"]) if view["own_review"] else None,
        "reviews": [
            _review_response(review) for review in view["reviews"]
        ],
        "ai_assessment": ai_assessment,
    }


@router.post(
    "/batches/{batch_id}/cases/{case_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_case_review(
    batch_id: str,
    case_id: str,
    request: ReviewSubmissionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewResponse:
    _require_reviewer_or_admin(current_user)
    try:
        batch = _get_batch(db, batch_id)
        dataset = load_dataset_by_id(batch.dataset_id, batch.dataset_version)
        case_context = next(
            case for case in dataset.get("cases", []) if case["case_id"] == case_id
        )
        review = submit_review(
            db,
            batch_id=batch_id,
            case_id=case_id,
            reviewer_user_id=current_user.user_id,
            label=request.label,
            rationale=request.rationale,
            allowed_labels={
                str(label).strip().upper()
                for label in case_context.get("review_label_options", [])
            }
            or None,
        )
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Evaluation case was not found.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Dataset version is not available.") from exc
    except M66ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _review_response(review)


@router.get("/batches/{batch_id}/adjudications")
def adjudication_queue(
    batch_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, object]]:
    _require_platform_admin(current_user)
    batch = _get_batch(db, batch_id)
    dataset = load_dataset_by_id(batch.dataset_id, batch.dataset_version)
    cases_by_id = {case["case_id"]: case for case in dataset.get("cases", [])}
    cases = db.scalars(
        select(ReviewCaseDB).where(
            ReviewCaseDB.batch_id == batch.id,
            ReviewCaseDB.status == M66CaseReviewStatus.DISAGREEMENT,
        )
    ).all()
    return [
        {
            "case": cases_by_id.get(case.case_id),
            "status": case.status,
            "reviews": [_review_response(review) for review in case.reviews],
        }
        for case in cases
    ]


@router.post(
    "/batches/{batch_id}/cases/{case_id}/adjudication",
    response_model=dict[str, object],
)
def submit_case_adjudication(
    batch_id: str,
    case_id: str,
    request: AdjudicationSubmissionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _require_platform_admin(current_user)
    try:
        batch = _get_batch(db, batch_id)
        dataset = load_dataset_by_id(batch.dataset_id, batch.dataset_version)
        case_context = next(
            case for case in dataset.get("cases", []) if case["case_id"] == case_id
        )
        adjudication = submit_adjudication(
            db,
            batch_id=batch_id,
            case_id=case_id,
            adjudicator_user_id=current_user.user_id,
            final_label=request.final_label,
            rationale=request.rationale,
            allowed_labels={
                str(label).strip().upper()
                for label in case_context.get("review_label_options", [])
            }
            or None,
        )
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Evaluation case was not found.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail="Dataset version is not available.") from exc
    except M66ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": adjudication.id,
        "case_id": adjudication.case_id,
        "final_label": adjudication.final_label,
        "rationale": adjudication.rationale,
        "adjudicated_at": adjudication.adjudicated_at,
    }


@router.get("/batches/{batch_id}/progress", response_model=ReviewProgressResponse)
def review_progress(
    batch_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReviewProgressResponse:
    _require_platform_admin(current_user)
    batch = _get_batch(db, batch_id)
    cases = db.scalars(
        select(ReviewCaseDB).where(ReviewCaseDB.batch_id == batch.id)
    ).all()
    dataset = load_dataset_by_id(batch.dataset_id, batch.dataset_version)
    dataset_cases = {
        case["case_id"]: case
        for case in dataset.get("cases", [])
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    counts = {
        "awaiting_first_review": 0,
        "awaiting_second_review": 0,
        "reviewed": 0,
        "agreed": 0,
        "disagreement": 0,
        "adjudicated": 0,
    }
    for case in cases:
        if len(case.reviews) == 0:
            counts["awaiting_first_review"] += 1
        elif batch.review_mode == "SINGLE_REVIEWER" and case.status == M66CaseReviewStatus.REVIEWED:
            counts["reviewed"] += 1
        elif len(case.reviews) == 1:
            counts["awaiting_second_review"] += 1
        elif case.status == M66CaseReviewStatus.AGREED:
            counts["agreed"] += 1
        elif case.status == M66CaseReviewStatus.DISAGREEMENT:
            counts["disagreement"] += 1
        elif case.status == M66CaseReviewStatus.ADJUDICATED:
            counts["adjudicated"] += 1
    category_counts: dict[str, dict[str, object]] = {}
    for review_case in cases:
        category = dataset_cases.get(review_case.case_id, {}).get(
            "category", "uncategorized"
        )
        summary = category_counts.setdefault(
            str(category),
            {
                "category": str(category),
                "total_cases": 0,
                "reviewed_cases": 0,
                "agreed_cases": 0,
                "disagreement_cases": 0,
                "adjudicated_cases": 0,
                "last_reviewed_at": None,
            },
        )
        summary["total_cases"] = int(summary["total_cases"]) + 1
        if review_case.reviews:
            summary["reviewed_cases"] = int(summary["reviewed_cases"]) + 1
            latest_review = max(
                review_case.reviews,
                key=lambda review: review.submitted_at,
            )
            latest_review_at = latest_review.submitted_at.isoformat()
            if (
                summary["last_reviewed_at"] is None
                or latest_review_at > str(summary["last_reviewed_at"])
            ):
                summary["last_reviewed_at"] = latest_review_at
        if review_case.status == M66CaseReviewStatus.AGREED:
            summary["agreed_cases"] = int(summary["agreed_cases"]) + 1
        elif review_case.status == M66CaseReviewStatus.DISAGREEMENT:
            summary["disagreement_cases"] = int(summary["disagreement_cases"]) + 1
        elif review_case.status == M66CaseReviewStatus.ADJUDICATED:
            summary["adjudicated_cases"] = int(summary["adjudicated_cases"]) + 1
    latest_experiment = db.scalar(
        select(ReliabilityExperimentDB)
        .where(
            ReliabilityExperimentDB.dataset_id == batch.dataset_id,
            ReliabilityExperimentDB.dataset_version == batch.dataset_version,
        )
        .order_by(ReliabilityExperimentDB.created_at.desc())
    )
    evaluated_case_ids: set[str] = set()
    evaluation_attempt_count = 0
    if latest_experiment is not None:
        attempts = db.scalars(
            select(ReliabilityAttemptDB).where(
                ReliabilityAttemptDB.experiment_id == latest_experiment.id,
                ReliabilityAttemptDB.status == "SUCCEEDED",
            )
        ).all()
        evaluation_attempt_count = len(attempts)
        evaluated_case_ids = {attempt.case_id for attempt in attempts}
    for summary in category_counts.values():
        category = str(summary["category"])
        category_case_ids = {
            case_id
            for case_id, case in dataset_cases.items()
            if str(case.get("category", "uncategorized")) == category
        }
        summary["evaluated_cases"] = len(evaluated_case_ids & category_case_ids)
    return ReviewProgressResponse(
        batch=_batch_response(batch),
        total_cases=len(cases),
        category_progress=sorted(
            category_counts.values(), key=lambda item: str(item["category"])
        ),
        evaluation={
            "status": latest_experiment.status if latest_experiment else "NOT_STARTED",
            "experiment_id": latest_experiment.id if latest_experiment else None,
            "started_at": (
                latest_experiment.started_at.isoformat()
                if latest_experiment and latest_experiment.started_at
                else None
            ),
            "finished_at": (
                latest_experiment.finished_at.isoformat()
                if latest_experiment and latest_experiment.finished_at
                else None
            ),
            "evaluated_case_count": len(evaluated_case_ids),
            "attempt_count": evaluation_attempt_count,
        },
        **counts,
    )


@router.get("/batches/{batch_id}/audit")
def review_audit(
    batch_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, object]]:
    _require_platform_admin(current_user)
    _get_batch(db, batch_id)
    events = db.scalars(
        select(ReviewAuditEventDB)
        .where(ReviewAuditEventDB.batch_id == batch_id)
        .order_by(ReviewAuditEventDB.created_at, ReviewAuditEventDB.id)
    ).all()
    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "actor_user_id": event.actor_user_id,
            "entity_id": event.entity_id,
            "details": event.details,
            "created_at": event.created_at,
        }
        for event in events
    ]


def _review_response(review: ReviewDB | None) -> ReviewResponse:
    if review is None:
        raise ValueError("A review is required.")
    return ReviewResponse(
        id=review.id,
        case_id=review.case_id,
        reviewer_user_id=review.reviewer_user_id,
        label=review.label,
        rationale=review.rationale,
        submitted_at=review.submitted_at.isoformat(),
    )
