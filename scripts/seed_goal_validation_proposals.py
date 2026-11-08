"""Seed the supplied Goal Validation proposal dataset as a separate review batch."""

import argparse
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.human_review import (
    BenchmarkCaseVersionDB,
    BenchmarkReviewProposalDB,
    ReviewBatchDB,
    ReviewDB,
)
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.evaluation.review_datasets import (
    PROPOSAL_DATASET_ID,
    PROPOSAL_DATASET_VERSION,
    PROPOSAL_SOURCE_PATH,
    load_proposal_dataset,
    load_review_dataset_by_id,
)
from app.services.human_review import create_review_batch, register_benchmark_dataset


def seed_proposals(
    db: Session, *, actor_user_id: str, reviewer_ids: list[str], apply: bool = False
) -> dict:
    actor = db.get(UserDB, actor_user_id)
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise ValueError("An active platform administrator must initiate the review batch.")
    if len(reviewer_ids) != 2 or len(set(reviewer_ids)) != 2:
        raise ValueError("Two distinct reviewers are required.")
    for reviewer_id in reviewer_ids:
        reviewer = db.get(UserDB, reviewer_id)
        if reviewer is None or not reviewer.is_active or not reviewer.is_reviewer:
            raise ValueError(f"Reviewer {reviewer_id} is not an active dedicated reviewer.")

    source = load_proposal_dataset()
    dataset = load_review_dataset_by_id(PROPOSAL_DATASET_ID, PROPOSAL_DATASET_VERSION)
    case_ids = [case.case_id for case in source.cases]
    batch = db.scalar(
        select(ReviewBatchDB).where(
            ReviewBatchDB.dataset_id == PROPOSAL_DATASET_ID,
            ReviewBatchDB.dataset_version == PROPOSAL_DATASET_VERSION,
        )
    )
    if batch is not None:
        assignments = {
            case.case_id: {assignment.reviewer_user_id for assignment in case.assignments}
            for case in batch.cases
        }
        if (
            batch.review_mode != "DUAL_ADJUDICATED"
            or set(assignments) != set(case_ids)
            or any(ids != set(reviewer_ids) for ids in assignments.values())
        ):
            raise ValueError("Existing batch cases or assignments differ; no changes were made.")
    summary = {
        "dataset_id": PROPOSAL_DATASET_ID,
        "dataset_version": PROPOSAL_DATASET_VERSION,
        "case_count": len(case_ids),
        "reviewer_ids": reviewer_ids,
        "proposal_count": len(case_ids),
        "assignments": len(case_ids) * 2,
        "proposal_status": "PROPOSED_NOT_HUMAN_APPROVED",
        "review_mode": "DUAL_ADJUDICATED",
        "visibility": "BEFORE_PROPOSAL_ASSISTED_REVIEW",
        "batch_id": batch.id if batch else None,
        "created": False,
        "dry_run": not apply,
    }
    if not apply:
        return summary

    register_benchmark_dataset(
        db,
        dataset=dataset,
        dataset_id=PROPOSAL_DATASET_ID,
        dataset_version=PROPOSAL_DATASET_VERSION,
        actor_user_id=actor_user_id,
    )
    db.flush()
    case_versions = {
        case.case_id: case
        for case in db.scalars(
            select(BenchmarkCaseVersionDB).where(
                BenchmarkCaseVersionDB.dataset_id == PROPOSAL_DATASET_ID,
                BenchmarkCaseVersionDB.dataset_version == PROPOSAL_DATASET_VERSION,
            )
        ).all()
    }
    if set(case_versions) != set(case_ids):
        raise ValueError("Registered catalogue cases do not match the proposal dataset.")
    existing_reviews = db.scalar(
        select(ReviewDB.id).where(
            ReviewDB.dataset_id == PROPOSAL_DATASET_ID,
            ReviewDB.dataset_version == PROPOSAL_DATASET_VERSION,
        ).limit(1)
    )
    now = datetime.now(UTC)
    for case in source.cases:
        version = case_versions[case.case_id]
        suggestion = case.ai_suggestion
        existing = db.scalar(
            select(BenchmarkReviewProposalDB).where(
                BenchmarkReviewProposalDB.case_version_id == version.id,
                BenchmarkReviewProposalDB.source_document == PROPOSAL_SOURCE_PATH.name,
            )
        )
        expected = {
            "proposed_label": suggestion.suggested_label.value,
            "rationale": suggestion.rationale,
            "provisional_expected_label": None,
            "confidence": None,
            "evidence_mapping_ids": [],
            "review_flags": [],
            "requires_owner_attention": False,
            "source_dataset_id": PROPOSAL_DATASET_ID,
            "source_dataset_version": PROPOSAL_DATASET_VERSION,
        }
        if existing is not None:
            if any(getattr(existing, key) != value for key, value in expected.items()):
                raise ValueError(f"{case.case_id}: existing proposal differs; no overwrite allowed.")
            continue
        if existing_reviews:
            raise ValueError("Cannot add proposals after review has begun.")
        db.add(
            BenchmarkReviewProposalDB(
                id=hashlib.sha256(
                    f"{version.id}:{PROPOSAL_SOURCE_PATH.name}".encode()
                ).hexdigest(),
                case_version_id=version.id,
                source_document=PROPOSAL_SOURCE_PATH.name,
                status="PROPOSED",
                created_at=now,
                created_by=actor_user_id,
                **expected,
            )
        )
    db.flush()
    if batch is None:
        batch = create_review_batch(
            db,
            dataset_id=PROPOSAL_DATASET_ID,
            dataset_version=PROPOSAL_DATASET_VERSION,
            case_ids=case_ids,
            started_by_user_id=actor_user_id,
            assignments={case_id: reviewer_ids for case_id in case_ids},
            review_mode="DUAL_ADJUDICATED",
        )
        summary["created"] = True
    else:
        db.commit()
    summary["batch_id"] = batch.id
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-user-id", required=True)
    parser.add_argument("--reviewer-ids", nargs=2, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        result = seed_proposals(
            db, actor_user_id=args.actor_user_id, reviewer_ids=args.reviewer_ids, apply=args.apply
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
