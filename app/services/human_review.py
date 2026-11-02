from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.human_review import (
    AdjudicationDB,
    ReviewAssignmentDB,
    ReviewAuditEventDB,
    ReviewBatchDB,
    ReviewCaseDB,
    ReviewDB,
)
from app.models.goal_criteria import GoalCriterionResult
from app.models.human_review import M66CaseReviewStatus, M66DatasetReviewStatus

M66_REVIEW_LABELS = {label.value for label in GoalCriterionResult}
M66_REVIEW_LABELS.update(
    {
        "VALID",
        "INVALID",
        "SMART",
        "NOT_SMART",
        "ACHIEVABLE",
        "NOT_ACHIEVABLE",
        "CLEAR",
        "UNCLEAR",
        "CURRENT",
        "OUTDATED",
        "SUPPORTED",
        "UNSUPPORTED",
        "GROUNDED",
        "UNGROUNDED",
    }
)


class M66ReviewError(ValueError):
    """Raised when a human-review workflow rule is violated."""


def create_review_batch(
    db: Session,
    *,
    dataset_id: str,
    dataset_version: str,
    case_ids: list[str],
    started_by_user_id: str,
    assignments: dict[str, list[str]],
    review_mode: str = "DUAL_ADJUDICATED",
    batch_id: str | None = None,
    started_at: datetime | None = None,
) -> ReviewBatchDB:
    if not dataset_id.strip() or not dataset_version.strip():
        raise M66ReviewError("Dataset ID and version are required.")
    if review_mode not in {"SINGLE_REVIEWER", "DUAL_ADJUDICATED"}:
        raise M66ReviewError("Review mode must be SINGLE_REVIEWER or DUAL_ADJUDICATED.")
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise M66ReviewError("A review batch requires unique cases.")
    if set(assignments) != set(case_ids):
        raise M66ReviewError("Every case must have assigned reviewers.")

    existing = db.scalar(
        select(ReviewBatchDB).where(
            ReviewBatchDB.dataset_id == dataset_id,
            ReviewBatchDB.dataset_version == dataset_version,
        )
    )
    if existing is not None:
        raise M66ReviewError("This dataset version already has a review batch.")

    now = started_at or datetime.now(UTC)
    batch = ReviewBatchDB(
        id=batch_id or str(uuid4()),
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        review_mode=review_mode,
        status=M66DatasetReviewStatus.DRAFT_UNREVIEWED,
        expected_case_count=len(case_ids),
        started_by_user_id=started_by_user_id,
        started_at=now,
    )
    db.add(batch)
    db.flush()
    for case_id in case_ids:
        reviewers = assignments[case_id]
        expected_reviewer_count = 1 if review_mode == "SINGLE_REVIEWER" else 2
        if (
            len(reviewers) != expected_reviewer_count
            or len(set(reviewers)) != expected_reviewer_count
        ):
            raise M66ReviewError(
                f"Case {case_id} must have {expected_reviewer_count} distinct assigned reviewer(s)."
            )
        case = ReviewCaseDB(
            id=f"{batch.id}:{case_id}",
            batch_id=batch.id,
            case_id=case_id,
            status=M66CaseReviewStatus.PENDING_REVIEW,
        )
        db.add(case)
        for slot, reviewer_id in enumerate(reviewers, start=1):
            db.add(
                ReviewAssignmentDB(
                    id=str(uuid4()),
                    case_record_id=case.id,
                    reviewer_user_id=reviewer_id,
                    slot=slot,
                    assigned_by_user_id=started_by_user_id,
                    assigned_at=now,
                )
            )
    _audit(
        db,
        batch=batch,
        actor_user_id=started_by_user_id,
        event_type="REVIEW_BATCH_STARTED",
        entity_id=batch.id,
        details={"case_count": len(case_ids)},
        created_at=now,
    )
    db.commit()
    db.refresh(batch)
    return batch


def submit_review(
    db: Session,
    *,
    batch_id: str,
    case_id: str,
    reviewer_user_id: str,
    label: str,
    rationale: str,
    allowed_labels: set[str] | None = None,
    review_id: str | None = None,
    submitted_at: datetime | None = None,
) -> ReviewDB:
    normalized_label = label.strip().upper()
    normalized_rationale = rationale.strip()
    if normalized_label not in (allowed_labels or M66_REVIEW_LABELS):
        raise M66ReviewError("The review label is not allowed for this evaluation case.")
    if not normalized_rationale:
        raise M66ReviewError("Review rationale is required.")

    case = _get_case(db, batch_id, case_id)
    assignment = db.scalar(
        select(ReviewAssignmentDB).where(
            ReviewAssignmentDB.case_record_id == case.id,
            ReviewAssignmentDB.reviewer_user_id == reviewer_user_id,
        )
    )
    if assignment is None:
        raise M66ReviewError("The reviewer is not assigned to this case.")
    if db.scalar(
        select(ReviewDB).where(
            ReviewDB.case_record_id == case.id,
            ReviewDB.reviewer_user_id == reviewer_user_id,
        )
    ) is not None:
        raise M66ReviewError("A reviewer cannot submit a case review twice.")
    if case.status in {
        M66CaseReviewStatus.REVIEWED,
        M66CaseReviewStatus.AGREED,
        M66CaseReviewStatus.ADJUDICATED,
    }:
        raise M66ReviewError("This case is no longer accepting independent reviews.")

    now = submitted_at or datetime.now(UTC)
    review = ReviewDB(
        id=review_id or str(uuid4()),
        case_record_id=case.id,
        dataset_id=case.batch.dataset_id,
        dataset_version=case.batch.dataset_version,
        case_id=case.case_id,
        reviewer_user_id=reviewer_user_id,
        label=normalized_label,
        rationale=normalized_rationale,
        submitted_at=now,
    )
    db.add(review)
    db.flush()
    _recalculate_case(db, case)
    _recalculate_batch(db, case.batch)
    _audit(
        db,
        batch=case.batch,
        case=case,
        actor_user_id=reviewer_user_id,
        event_type="REVIEW_SUBMITTED",
        entity_id=review.id,
        details={"label": review.label},
        created_at=now,
    )
    db.commit()
    db.refresh(review)
    return review


def get_case_for_reviewer(
    db: Session,
    *,
    batch_id: str,
    case_id: str,
    reviewer_user_id: str,
) -> dict[str, object]:
    case = _get_case(db, batch_id, case_id)
    assignment = db.scalar(
        select(ReviewAssignmentDB).where(
            ReviewAssignmentDB.case_record_id == case.id,
            ReviewAssignmentDB.reviewer_user_id == reviewer_user_id,
        )
    )
    if assignment is None:
        raise M66ReviewError("The reviewer is not assigned to this case.")
    own_review = db.scalar(
        select(ReviewDB).where(
            ReviewDB.case_record_id == case.id,
            ReviewDB.reviewer_user_id == reviewer_user_id,
        )
    )
    reviews = db.scalars(
        select(ReviewDB)
        .where(
            ReviewDB.case_record_id == case.id,
            ReviewDB.reviewer_user_id == reviewer_user_id
            if own_review is None
            else True,
        )
        .order_by(ReviewDB.submitted_at, ReviewDB.id)
    ).all()
    return {
        "case": case,
        "own_review": own_review,
        "reviews": reviews,
    }


def submit_adjudication(
    db: Session,
    *,
    batch_id: str,
    case_id: str,
    adjudicator_user_id: str,
    final_label: str,
    rationale: str,
    adjudication_id: str | None = None,
    adjudicated_at: datetime | None = None,
) -> AdjudicationDB:
    normalized_label = final_label.strip().upper()
    normalized_rationale = rationale.strip()
    if normalized_label not in M66_REVIEW_LABELS:
        raise M66ReviewError("The adjudication label is not a canonical M6.6 result.")
    if not normalized_rationale:
        raise M66ReviewError("Adjudication rationale is required.")

    case = _get_case(db, batch_id, case_id)
    reviews = db.scalars(
        select(ReviewDB)
        .where(ReviewDB.case_record_id == case.id)
        .order_by(ReviewDB.submitted_at, ReviewDB.id)
    ).all()
    if len(reviews) != 2 or len({review.reviewer_user_id for review in reviews}) != 2:
        raise M66ReviewError("Adjudication requires two distinct independent reviews.")
    if case.status != M66CaseReviewStatus.DISAGREEMENT:
        raise M66ReviewError("Only a disagreement can be adjudicated.")
    if adjudicator_user_id in {review.reviewer_user_id for review in reviews}:
        raise M66ReviewError("The adjudicator must be distinct from both reviewers.")
    if db.scalar(
        select(AdjudicationDB).where(AdjudicationDB.case_record_id == case.id)
    ) is not None:
        raise M66ReviewError("This case already has an adjudication.")

    now = adjudicated_at or datetime.now(UTC)
    adjudication = AdjudicationDB(
        id=adjudication_id or str(uuid4()),
        case_record_id=case.id,
        dataset_id=case.batch.dataset_id,
        dataset_version=case.batch.dataset_version,
        case_id=case.case_id,
        review_1_id=reviews[0].id,
        review_2_id=reviews[1].id,
        adjudicator_user_id=adjudicator_user_id,
        final_label=normalized_label,
        rationale=normalized_rationale,
        adjudicated_at=now,
    )
    db.add(adjudication)
    case.status = M66CaseReviewStatus.ADJUDICATED
    _recalculate_batch(db, case.batch)
    _audit(
        db,
        batch=case.batch,
        case=case,
        actor_user_id=adjudicator_user_id,
        event_type="ADJUDICATION_SUBMITTED",
        entity_id=adjudication.id,
        details={"final_label": adjudication.final_label},
        created_at=now,
    )
    db.commit()
    db.refresh(adjudication)
    return adjudication


def _get_case(db: Session, batch_id: str, case_id: str) -> ReviewCaseDB:
    case = db.scalar(
        select(ReviewCaseDB).where(
            ReviewCaseDB.batch_id == batch_id,
            ReviewCaseDB.case_id == case_id,
        )
    )
    if case is None:
        raise M66ReviewError("The case does not belong to this review batch.")
    return case


def _recalculate_case(db: Session, case: ReviewCaseDB) -> None:
    reviews = db.scalars(
        select(ReviewDB).where(ReviewDB.case_record_id == case.id)
    ).all()
    if case.batch.review_mode == "SINGLE_REVIEWER":
        case.status = (
            M66CaseReviewStatus.REVIEWED
            if len(reviews) == 1
            else M66CaseReviewStatus.PENDING_REVIEW
        )
    elif len(reviews) < 2:
        case.status = M66CaseReviewStatus.PENDING_REVIEW
    elif reviews[0].label == reviews[1].label:
        case.status = M66CaseReviewStatus.AGREED
    else:
        case.status = M66CaseReviewStatus.DISAGREEMENT


def _recalculate_batch(db: Session, batch: ReviewBatchDB) -> None:
    cases = db.scalars(
        select(ReviewCaseDB).where(ReviewCaseDB.batch_id == batch.id)
    ).all()
    if len(cases) != batch.expected_case_count:
        batch.status = M66DatasetReviewStatus.REVIEW_BLOCKED
        batch.completed_at = None
    elif all(case.status in {
        M66CaseReviewStatus.REVIEWED,
        M66CaseReviewStatus.AGREED,
        M66CaseReviewStatus.ADJUDICATED,
    } for case in cases):
        batch.status = M66DatasetReviewStatus.HUMAN_REVIEWED
        batch.completed_at = datetime.now(UTC)
    else:
        batch.status = M66DatasetReviewStatus.IN_REVIEW
        batch.completed_at = None


def _audit(
    db: Session,
    *,
    batch: ReviewBatchDB,
    actor_user_id: str,
    event_type: str,
    entity_id: str,
    details: dict[str, object],
    created_at: datetime,
    case: ReviewCaseDB | None = None,
) -> None:
    db.add(
        ReviewAuditEventDB(
            id=str(uuid4()),
            batch_id=batch.id,
            case_record_id=case.id if case else None,
            event_type=event_type,
            actor_user_id=actor_user_id,
            entity_id=entity_id,
            details=details,
            created_at=created_at,
        )
    )
