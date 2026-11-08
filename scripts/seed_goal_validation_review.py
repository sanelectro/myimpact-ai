"""Register the Goal Validation benchmark and assign independent human reviewers."""

import argparse
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.human_review import ReviewBatchDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.evaluation.goal_validation_benchmark import DATASET_VERSION
from app.evaluation.review_datasets import load_review_dataset_by_id
from app.services.human_review import create_review_batch, register_benchmark_dataset

DATASET_ID = "goal-validation"


def seed_review(
    db: Session,
    *,
    actor_user_id: str,
    reviewer_ids: list[str],
    apply: bool = False,
) -> dict:
    actor = db.get(UserDB, actor_user_id)
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise ValueError("An active platform administrator must initiate the review batch.")
    if len(reviewer_ids) != 2 or len(set(reviewer_ids)) != 2:
        raise ValueError("Two distinct dedicated reviewers are required.")
    for reviewer_id in reviewer_ids:
        reviewer = db.get(UserDB, reviewer_id)
        if reviewer is None or not reviewer.is_active or not reviewer.is_reviewer:
            raise ValueError(f"Reviewer {reviewer_id} is not an active dedicated reviewer.")
    dataset = load_review_dataset_by_id(DATASET_ID, DATASET_VERSION)
    case_ids = [case["case_id"] for case in dataset["cases"]]
    existing = db.scalar(
        select(ReviewBatchDB).where(
            ReviewBatchDB.dataset_id == DATASET_ID,
            ReviewBatchDB.dataset_version == DATASET_VERSION,
        )
    )
    summary = {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "case_count": len(case_ids),
        "reviewer_ids": reviewer_ids,
        "assignments": len(case_ids) * 2,
        "label_status": "DRAFT_UNREVIEWED",
        "human_review": "PENDING",
        "threshold_approval": "NOT_APPROVED",
        "batch_id": existing.id if existing else None,
        "created": False,
        "dry_run": not apply,
    }
    if existing is not None:
        existing_assignments = {
            case.case_id: {assignment.reviewer_user_id for assignment in case.assignments}
            for case in existing.cases
        }
        if (
            existing.review_mode != "DUAL_ADJUDICATED"
            or set(existing_assignments) != set(case_ids)
            or any(ids != set(reviewer_ids) for ids in existing_assignments.values())
        ):
            raise ValueError("The existing batch has different cases or assignments; it was not changed.")
    if not apply:
        return summary
    register_benchmark_dataset(
        db,
        dataset=dataset,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        actor_user_id=actor_user_id,
    )
    if existing is not None:
        db.commit()
        summary["human_review"] = existing.status.value
        return summary
    batch = create_review_batch(
        db,
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        case_ids=case_ids,
        started_by_user_id=actor_user_id,
        assignments={case_id: reviewer_ids for case_id in case_ids},
        review_mode="DUAL_ADJUDICATED",
    )
    summary.update(batch_id=batch.id, created=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-user-id", required=True)
    parser.add_argument("--reviewer-ids", nargs=2, required=True)
    parser.add_argument("--apply", action="store_true", help="Persist the batch; otherwise inspect only.")
    args = parser.parse_args()
    with SessionLocal() as db:
        summary = seed_review(
            db,
            actor_user_id=args.actor_user_id,
            reviewer_ids=args.reviewer_ids,
            apply=args.apply,
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
