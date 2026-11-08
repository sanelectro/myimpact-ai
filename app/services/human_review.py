import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.human_review import (
    AdjudicationDB,
    BenchmarkCaseVersionDB,
    BenchmarkCategoryDB,
    BenchmarkDatasetVersionDB,
    BenchmarkDimensionDB,
    BenchmarkLabelDB,
    BenchmarkReviewProposalDB,
    HumanAIComparisonDB,
    ReviewAssignmentDB,
    ReviewAuditEventDB,
    ReviewBatchDB,
    ReviewCaseDB,
    ReviewDB,
)
from app.db.models.reliability import ReliabilityAttemptDB, ReliabilityExperimentDB
from app.evaluation.review_datasets import PROPOSAL_DATASET_ID, PROPOSAL_DATASET_VERSION
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
PRIMARY_REVIEW_STAGES = {"BLIND", "PROPOSAL_ASSISTED"}


class M66ReviewError(ValueError):
    """Raised when a human-review workflow rule is violated."""


@dataclass
class BatchReviewPreview:
    batch: ReviewBatchDB
    cases: list[ReviewCaseDB]
    reviews: list[ReviewDB]
    preview_token: str

    @property
    def is_final(self) -> bool:
        return len(self.reviews) == len(self.cases) and all(
            review.is_final for review in self.reviews
        )

    @property
    def can_finalize(self) -> bool:
        return len(self.reviews) == len(self.cases) and not self.is_final


def get_batch_review_preview(
    db: Session, *, batch_id: str, reviewer_user_id: str
) -> BatchReviewPreview:
    batch = db.get(ReviewBatchDB, batch_id)
    if batch is None:
        raise M66ReviewError("Review batch was not found.")
    cases = list(db.scalars(
        select(ReviewCaseDB)
        .where(
            ReviewCaseDB.batch_id == batch_id,
            ReviewCaseDB.assignments.any(
                ReviewAssignmentDB.reviewer_user_id == reviewer_user_id
            ),
        )
        .order_by(ReviewCaseDB.case_id)
    ).all())
    if not cases:
        raise M66ReviewError("The reviewer has no assigned cases in this batch.")
    reviews = list(db.scalars(
        select(ReviewDB)
        .where(
            ReviewDB.case_record_id.in_([case.id for case in cases]),
            ReviewDB.reviewer_user_id == reviewer_user_id,
            ReviewDB.review_stage.in_(PRIMARY_REVIEW_STAGES),
        )
        .order_by(ReviewDB.case_id, ReviewDB.id)
        .execution_options(populate_existing=True)
    ).all())
    if len({review.case_record_id for review in reviews}) != len(reviews):
        raise M66ReviewError("A case has multiple primary reviews; resolve them before final submission.")
    snapshot = {
        "batch_id": batch_id,
        "reviewer_user_id": reviewer_user_id,
        "case_ids": [case.id for case in cases],
        "case_content_hashes": [
            {"id": case_version.id, "content_hash": case_version.content_hash}
            for case_version in db.scalars(
                select(BenchmarkCaseVersionDB)
                .where(BenchmarkCaseVersionDB.id.in_(
                    [case.case_version_id for case in cases if case.case_version_id]
                ))
                .order_by(BenchmarkCaseVersionDB.id)
                .execution_options(populate_existing=True)
            ).all()
        ],
        "reviews": [
            {
                "id": review.id,
                "case_id": review.case_id,
                "label": review.label,
                "rationale": review.rationale,
                "review_stage": review.review_stage,
                "reference_proposal_id": review.reference_proposal_id,
                "confidence": review.confidence,
                "context_notes": review.context_notes,
                "evidence_findings": review.evidence_findings,
                "updated_at": review.updated_at.isoformat() if review.updated_at else None,
                "is_final": review.is_final,
            }
            for review in reviews
        ],
    }
    token = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return BatchReviewPreview(batch, cases, reviews, token)


def finalize_batch_reviews(
    db: Session, *, batch_id: str, reviewer_user_id: str, preview_token: str
) -> BatchReviewPreview:
    _lock_review_batch(db, batch_id)
    preview = get_batch_review_preview(
        db, batch_id=batch_id, reviewer_user_id=reviewer_user_id
    )
    if preview.is_final:
        raise M66ReviewError("Your final review has already been submitted.")
    if not preview.can_finalize:
        raise M66ReviewError("Submit a review for every assigned case before final submission.")
    if preview.preview_token != preview_token:
        raise M66ReviewError("Your reviews changed after this preview. Reload the preview before final submission.")
    now = datetime.now(UTC)
    for review in preview.reviews:
        if review.is_final:
            continue
        review.is_final = True
        review.submitted_at = now
        review.updated_at = now
        _audit(
            db,
            batch=preview.batch,
            case=review.case,
            actor_user_id=reviewer_user_id,
            event_type=f"{review.review_stage}_REVIEW_SUBMITTED",
            entity_id=review.id,
            details={
                "label": review.label,
                "rationale": review.rationale,
                "review_stage": review.review_stage,
                "is_final": True,
                "reference_proposal_id": review.reference_proposal_id,
                "preview_token": preview_token,
            },
            created_at=now,
        )
    db.flush()
    for case in preview.cases:
        if case.status != M66CaseReviewStatus.ADJUDICATED:
            _recalculate_case(db, case)
    db.flush()
    _recalculate_batch(db, preview.batch)
    _audit(
        db,
        batch=preview.batch,
        actor_user_id=reviewer_user_id,
        event_type="REVIEWER_BATCH_FINAL_SUBMITTED",
        entity_id=preview.batch.id,
        details={
            "review_ids": [review.id for review in preview.reviews],
            "case_count": len(preview.cases),
            "preview_token": preview_token,
        },
        created_at=now,
    )
    db.commit()
    return get_batch_review_preview(
        db, batch_id=batch_id, reviewer_user_id=reviewer_user_id
    )


def _lock_review_batch(db: Session, batch_id: str) -> None:
    batch = db.scalar(
        select(ReviewBatchDB)
        .where(ReviewBatchDB.id == batch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if batch is None:
        raise M66ReviewError("Review batch was not found.")


def register_benchmark_dataset(
    db: Session,
    *,
    dataset: dict[str, object],
    dataset_id: str,
    dataset_version: str,
    actor_user_id: str,
    registered_at: datetime | None = None,
) -> BenchmarkDatasetVersionDB:
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise M66ReviewError("A benchmark dataset must contain at least one case.")
    if dataset.get("dataset_id") != dataset_id:
        raise M66ReviewError("The dataset ID does not match its catalogue document.")
    evaluation_record = dataset.get("evaluation_record")
    if not isinstance(evaluation_record, dict) or evaluation_record.get(
        "dataset_version"
    ) != dataset_version:
        raise M66ReviewError("The dataset version does not match its catalogue document.")

    canonical = json.dumps(dataset, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.scalar(
        select(BenchmarkDatasetVersionDB).where(
            BenchmarkDatasetVersionDB.dataset_id == dataset_id,
            BenchmarkDatasetVersionDB.dataset_version == dataset_version,
        )
    )
    is_legacy_catalogue = bool(
        existing is not None
        and existing.status == "LEGACY"
        and existing.content_hash == "legacy"
    )
    if existing is not None and not is_legacy_catalogue:
        if existing.content_hash != content_hash:
            raise M66ReviewError(
                "This dataset version is already registered with different content."
            )
        return existing

    now = registered_at or datetime.now(UTC)
    if existing is not None:
        record = existing
        record.content_hash = content_hash
        record.status = str(dataset.get("label_status", "DRAFT_UNREVIEWED"))
        record.case_count = len(cases)
    else:
        record = BenchmarkDatasetVersionDB(
            id=f"ds-{content_hash[:48]}",
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            content_hash=content_hash,
            status=str(dataset.get("label_status", "DRAFT_UNREVIEWED")),
            case_count=len(cases),
            created_at=now,
            created_by=actor_user_id,
        )
        db.add(record)
    db.flush()
    existing_case_versions = {
        case.case_id: case
        for case in db.scalars(
            select(BenchmarkCaseVersionDB).where(
                BenchmarkCaseVersionDB.dataset_id == dataset_id,
                BenchmarkCaseVersionDB.dataset_version == dataset_version,
            )
        ).all()
    }
    known_category_ids = set(db.scalars(select(BenchmarkCategoryDB.id)).all())
    known_dimension_ids = set(db.scalars(select(BenchmarkDimensionDB.id)).all())
    known_label_ids = set(db.scalars(select(BenchmarkLabelDB.id)).all())
    categories = evaluation_record.get("categories", [])
    dimensions = evaluation_record.get("benchmark_dimensions", [])
    for category in categories if isinstance(categories, list) else []:
        if isinstance(category, str) and category not in known_category_ids:
            db.add(
                BenchmarkCategoryDB(
                    id=category,
                    display_name=category.replace("_", " ").title(),
                    description=f"Benchmark category: {category}",
                    is_active=True,
                )
            )
            known_category_ids.add(category)
    for dimension in dimensions if isinstance(dimensions, list) else []:
        if isinstance(dimension, str) and dimension not in known_dimension_ids:
            db.add(
                BenchmarkDimensionDB(
                    id=dimension,
                    display_name=dimension.replace("_", " ").title(),
                    description=f"Benchmark dimension: {dimension}",
                    is_active=True,
                )
            )
            known_dimension_ids.add(dimension)
    db.flush()

    seen_case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise M66ReviewError("Every benchmark case must have a case ID.")
        case_id = case["case_id"]
        if case_id in seen_case_ids:
            raise M66ReviewError(f"Duplicate case ID in benchmark dataset: {case_id}.")
        seen_case_ids.add(case_id)
        category = str(case.get("category") or "uncategorized")
        case_json = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        case_hash = hashlib.sha256(case_json.encode("utf-8")).hexdigest()
        case_labels = case.get("review_label_options", [])
        if not isinstance(case_labels, list) or not all(
            isinstance(label, str) for label in case_labels
        ):
            raise M66ReviewError(f"Review labels are invalid for case {case_id}.")
        case_dimensions = case.get("benchmark_dimensions", dimensions)
        if not isinstance(case_dimensions, list) or not all(
            isinstance(dimension, str) for dimension in case_dimensions
        ):
            raise M66ReviewError(f"Benchmark dimensions are invalid for case {case_id}.")
        case_version_id = (
            f"cv-{hashlib.sha256(f'{dataset_id}:{dataset_version}:{case_id}'.encode()).hexdigest()[:48]}"
        )
        labels_data = case.get("labels")
        case_label_status = (
            labels_data.get("status") if isinstance(labels_data, dict) else None
        )
        label_status = (
            case_label_status
            if isinstance(case_label_status, str)
            else str(dataset.get("label_status", "DRAFT_UNREVIEWED"))
        )
        polarity = labels_data.get("polarity") if isinstance(labels_data, dict) else None
        case_version = existing_case_versions.get(case_id)
        if case_version is not None:
            is_legacy_case = (
                is_legacy_catalogue
                and case_version.label_status == "LEGACY"
                and case_version.content_hash == "legacy"
            )
            if not is_legacy_case and case_version.content_hash != case_hash:
                raise M66ReviewError(
                    f"Case {case_id} already exists with different versioned content."
                )
            if is_legacy_case:
                case_version.category = category
                case_version.content_hash = case_hash
                case_version.case_json = case
                case_version.label_options = [
                    label.strip().upper() for label in case_labels
                ]
                case_version.dimensions = case_dimensions
                case_version.polarity = polarity if isinstance(polarity, str) else None
                case_version.label_status = label_status
        else:
            case_version = BenchmarkCaseVersionDB(
                id=case_version_id,
                dataset_version_id=record.id,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                case_id=case_id,
                category=category,
                content_hash=case_hash,
                case_json=case,
                label_options=[label.strip().upper() for label in case_labels],
                dimensions=case_dimensions,
                polarity=polarity if isinstance(polarity, str) else None,
                label_status=label_status,
                created_at=now,
                created_by=actor_user_id,
            )
            db.add(case_version)
            existing_case_versions[case_id] = case_version
        if category not in known_category_ids:
            db.add(
                BenchmarkCategoryDB(
                    id=category,
                    display_name=category.replace("_", " ").title(),
                    description=f"Benchmark category: {category}",
                    is_active=True,
                )
            )
            known_category_ids.add(category)
        for label in case_labels:
            normalized_label = label.strip().upper()
            label_id = hashlib.sha256(
                f"{category}:{normalized_label}".encode()
            ).hexdigest()[:64]
            if label_id not in known_label_ids:
                db.add(
                    BenchmarkLabelDB(
                        id=label_id,
                        category_id=category,
                        label=normalized_label,
                        polarity=None,
                        is_active=True,
                    )
                )
                known_label_ids.add(label_id)
    return record


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
    dataset_version_record = db.scalar(
        select(BenchmarkDatasetVersionDB).where(
            BenchmarkDatasetVersionDB.dataset_id == dataset_id,
            BenchmarkDatasetVersionDB.dataset_version == dataset_version,
        )
    )
    case_versions = {
        case.case_id: case
        for case in (
            db.scalars(
                select(BenchmarkCaseVersionDB).where(
                    BenchmarkCaseVersionDB.dataset_id == dataset_id,
                    BenchmarkCaseVersionDB.dataset_version == dataset_version,
                )
            ).all()
            if dataset_version_record is not None
            else []
        )
    }
    batch = ReviewBatchDB(
        id=batch_id or str(uuid4()),
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        review_mode=review_mode,
        status=M66DatasetReviewStatus.DRAFT_UNREVIEWED,
        expected_case_count=len(case_ids),
        started_by_user_id=started_by_user_id,
        started_at=now,
        created_at=now,
        created_by=started_by_user_id,
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
            case_version_id=(
                case_versions[case_id].id if case_id in case_versions else None
            ),
            category=(
                case_versions[case_id].category if case_id in case_versions else None
            ),
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
    review_stage: str = "BLIND",
    ai_attempt_id: str | None = None,
    reference_proposal_id: str | None = None,
    confidence: float | None = None,
    context_notes: str | None = None,
    evidence_findings: list[dict[str, object]] | None = None,
    review_id: str | None = None,
    submitted_at: datetime | None = None,
    is_final: bool = True,
) -> ReviewDB:
    normalized_label = label.strip().upper()
    normalized_rationale = rationale.strip()
    normalized_stage = review_stage.strip().upper()
    if normalized_stage not in {*PRIMARY_REVIEW_STAGES, "POST_AI"}:
        raise M66ReviewError("Review stage must be BLIND, PROPOSAL_ASSISTED, or POST_AI.")
    if normalized_label not in (allowed_labels or M66_REVIEW_LABELS):
        raise M66ReviewError("The review label is not allowed for this evaluation case.")
    if not normalized_rationale:
        raise M66ReviewError("Review rationale is required.")
    if confidence is not None and not 0 <= confidence <= 1:
        raise M66ReviewError("Review confidence must be between 0 and 1.")

    _lock_review_batch(db, batch_id)
    case = _get_case(db, batch_id, case_id)
    if (
        case.batch.dataset_id == "goal-validation"
        and normalized_stage == "PROPOSAL_ASSISTED"
    ):
        raise M66ReviewError(
            "Goal Validation requires a blind independent primary review."
        )
    if (
        case.batch.dataset_id == PROPOSAL_DATASET_ID
        and case.batch.dataset_version == PROPOSAL_DATASET_VERSION
        and normalized_stage == "BLIND"
    ):
        raise M66ReviewError("This Goal Validation batch requires a proposal-assisted primary review.")
    assignment = db.scalar(
        select(ReviewAssignmentDB).where(
            ReviewAssignmentDB.case_record_id == case.id,
            ReviewAssignmentDB.reviewer_user_id == reviewer_user_id,
        )
    )
    if assignment is None:
        raise M66ReviewError("The reviewer is not assigned to this case.")
    existing_review_query = select(ReviewDB).where(
        ReviewDB.case_record_id == case.id,
        ReviewDB.reviewer_user_id == reviewer_user_id,
    )
    if normalized_stage in PRIMARY_REVIEW_STAGES:
        existing_review_query = existing_review_query.where(
            ReviewDB.review_stage.in_(PRIMARY_REVIEW_STAGES)
        )
    else:
        existing_review_query = existing_review_query.where(
            ReviewDB.review_stage == normalized_stage
        )
    existing_review = db.scalar(
        existing_review_query.order_by(
            ReviewDB.updated_at.desc(),
            ReviewDB.submitted_at.desc(),
            ReviewDB.id,
        ).execution_options(populate_existing=True)
    )
    if existing_review is not None and existing_review.is_final:
        raise M66ReviewError("A finalized case review cannot be changed.")
    if normalized_stage == "BLIND":
        if ai_attempt_id is not None or reference_proposal_id is not None:
            raise M66ReviewError(
                "A blind review cannot reference an AI attempt or review proposal."
            )
    elif normalized_stage == "PROPOSAL_ASSISTED":
        if ai_attempt_id is not None:
            raise M66ReviewError("A proposal-assisted review cannot reference an AI attempt.")
        if not reference_proposal_id or case.case_version_id is None:
            raise M66ReviewError(
                "A proposal-assisted review must reference a proposal for this case."
            )
        reference_proposal = db.scalar(
            select(BenchmarkReviewProposalDB).where(
                BenchmarkReviewProposalDB.id == reference_proposal_id,
                BenchmarkReviewProposalDB.case_version_id == case.case_version_id,
                BenchmarkReviewProposalDB.source_dataset_id == case.batch.dataset_id,
                BenchmarkReviewProposalDB.source_dataset_version
                == case.batch.dataset_version,
                BenchmarkReviewProposalDB.status != "REJECTED",
            )
        )
        if reference_proposal is None:
            raise M66ReviewError(
                "The review proposal does not belong to this dataset case."
            )
    else:
        if reference_proposal_id is not None:
            raise M66ReviewError("A post-AI review cannot reference a review proposal.")
        if not ai_attempt_id:
            raise M66ReviewError("A post-AI review must reference an exact AI attempt.")
        if case.case_version_id is None:
            raise M66ReviewError("The case has no registered immutable dataset version.")
        primary_review = db.scalar(
            select(ReviewDB).where(
                ReviewDB.case_record_id == case.id,
                ReviewDB.reviewer_user_id == reviewer_user_id,
                ReviewDB.review_stage.in_(PRIMARY_REVIEW_STAGES),
                ReviewDB.is_final.is_(True),
            )
        )
        if primary_review is None:
            raise M66ReviewError("Finalize your primary review before the post-AI review.")
        attempt = db.scalar(
            select(ReliabilityAttemptDB)
            .join(
                ReliabilityExperimentDB,
                ReliabilityExperimentDB.id == ReliabilityAttemptDB.experiment_id,
            )
            .where(
                ReliabilityAttemptDB.id == ai_attempt_id,
                ReliabilityAttemptDB.case_id == case_id,
                ReliabilityAttemptDB.dataset_version == case.batch.dataset_version,
                ReliabilityAttemptDB.status == "SUCCEEDED",
                ReliabilityAttemptDB.normalized_output.is_not(None),
                ReliabilityExperimentDB.dataset_id == case.batch.dataset_id,
            )
        )
        if attempt is None:
            raise M66ReviewError(
                "The AI attempt must be a successful run for this exact dataset case."
            )
    if normalized_stage in PRIMARY_REVIEW_STAGES and case.status in {
        M66CaseReviewStatus.REVIEWED,
        M66CaseReviewStatus.AGREED,
        M66CaseReviewStatus.ADJUDICATED,
    }:
        raise M66ReviewError("This case is no longer accepting primary reviews.")

    now = submitted_at or datetime.now(UTC)
    previous_values = (
        {
            "review_stage": existing_review.review_stage,
            "label": existing_review.label,
            "rationale": existing_review.rationale,
            "confidence": existing_review.confidence,
            "context_notes": existing_review.context_notes,
            "evidence_findings": existing_review.evidence_findings,
            "is_final": existing_review.is_final,
        }
        if existing_review is not None
        else None
    )
    review = existing_review or ReviewDB(
        id=review_id or str(uuid4()),
        case_record_id=case.id,
        dataset_id=case.batch.dataset_id,
        dataset_version=case.batch.dataset_version,
        case_id=case.case_id,
        case_version_id=case.case_version_id,
        reviewer_user_id=reviewer_user_id,
        submitted_at=now,
    )
    review.review_stage = normalized_stage
    review.ai_attempt_id = ai_attempt_id
    review.reference_proposal_id = reference_proposal_id
    review.label = normalized_label
    review.rationale = normalized_rationale
    review.confidence = confidence
    review.context_notes = context_notes.strip() if context_notes else None
    review.evidence_findings = evidence_findings
    review.is_final = is_final
    review.updated_at = now
    if is_final:
        review.submitted_at = now
    if existing_review is None:
        db.add(review)
    db.flush()
    if normalized_stage in PRIMARY_REVIEW_STAGES and is_final:
        _recalculate_case(db, case)
        _recalculate_batch(db, case.batch)
    elif normalized_stage in PRIMARY_REVIEW_STAGES:
        _recalculate_batch(db, case.batch)
    elif normalized_stage == "POST_AI" and is_final:
        primary_review = db.scalar(
            select(ReviewDB).where(
                ReviewDB.case_record_id == case.id,
                ReviewDB.reviewer_user_id == reviewer_user_id,
                ReviewDB.review_stage.in_(PRIMARY_REVIEW_STAGES),
                ReviewDB.is_final.is_(True),
            )
        )
        attempt = db.get(ReliabilityAttemptDB, ai_attempt_id)
        if primary_review is None or attempt is None:
            raise M66ReviewError("The human-AI comparison requires versioned case data.")
        ai_label = (attempt.normalized_output or {}).get("assessment_label")
        db.add(
            HumanAIComparisonDB(
                id=str(uuid4()),
                case_record_id=case.id,
                case_version_id=case.case_version_id,
                blind_review_id=primary_review.id,
                post_ai_review_id=review.id,
                ai_attempt_id=attempt.id,
                agreement=(
                    primary_review.label == str(ai_label).strip().upper()
                    if ai_label is not None
                    else False
                ),
                comparison_json={
                    "blind_label": primary_review.label,
                    "post_ai_label": normalized_label,
                    "ai_label": ai_label,
                    "blind_ai_agreement": (
                        primary_review.label == str(ai_label).strip().upper()
                        if ai_label is not None
                        else None
                    ),
                    "post_ai_ai_agreement": (
                        normalized_label == str(ai_label).strip().upper()
                        if ai_label is not None
                        else None
                    ),
                },
                created_at=now,
            )
        )
    _audit(
        db,
        batch=case.batch,
        case=case,
        actor_user_id=reviewer_user_id,
        event_type=(
            f"{normalized_stage}_REVIEW_SUBMITTED"
            if is_final
            else f"{normalized_stage}_REVIEW_DRAFT_SAVED"
        ),
        entity_id=review.id,
        details={
            "label": review.label,
            "rationale": review.rationale,
            "review_stage": normalized_stage,
            "is_final": is_final,
            "ai_attempt_id": ai_attempt_id,
            "reference_proposal_id": reference_proposal_id,
            "previous_review": previous_values,
        },
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
    review_stage: str = "BLIND",
    review_stages: set[str] | None = None,
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
    active_review_stages = review_stages or {review_stage}
    own_review = db.scalar(
        select(ReviewDB).where(
            ReviewDB.case_record_id == case.id,
            ReviewDB.reviewer_user_id == reviewer_user_id,
            ReviewDB.review_stage.in_(active_review_stages),
        ).order_by(
            ReviewDB.is_final.desc(),
            ReviewDB.updated_at.desc(),
            ReviewDB.submitted_at.desc(),
            ReviewDB.id,
        )
    )
    reviews = db.scalars(
        select(ReviewDB)
        .where(
            ReviewDB.case_record_id == case.id,
            ReviewDB.review_stage.in_(active_review_stages),
            ReviewDB.is_final.is_(True),
            ReviewDB.reviewer_user_id == reviewer_user_id
            if own_review is None or not own_review.is_final
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
    allowed_labels: set[str] | None = None,
    adjudication_id: str | None = None,
    adjudicated_at: datetime | None = None,
) -> AdjudicationDB:
    normalized_label = final_label.strip().upper()
    normalized_rationale = rationale.strip()
    if normalized_label not in (allowed_labels or M66_REVIEW_LABELS):
        raise M66ReviewError("The adjudication label is not a canonical M6.6 result.")
    if not normalized_rationale:
        raise M66ReviewError("Adjudication rationale is required.")

    case = _get_case(db, batch_id, case_id)
    reviews = db.scalars(
        select(ReviewDB)
        .where(
            ReviewDB.case_record_id == case.id,
            ReviewDB.review_stage.in_(PRIMARY_REVIEW_STAGES),
            ReviewDB.is_final.is_(True),
        )
        .order_by(ReviewDB.submitted_at, ReviewDB.id)
    ).all()
    if len(reviews) != 2 or len({review.reviewer_user_id for review in reviews}) != 2:
        raise M66ReviewError("Adjudication requires two distinct primary reviews.")
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
        select(ReviewDB).where(
            ReviewDB.case_record_id == case.id,
            ReviewDB.review_stage.in_(PRIMARY_REVIEW_STAGES),
            ReviewDB.is_final.is_(True),
        )
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
