"""Migrate existing Goal Validation review labels with an audit trail."""

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.human_review import (
    AdjudicationDB,
    BenchmarkCaseVersionDB,
    BenchmarkDatasetVersionDB,
    BenchmarkLabelDB,
    BenchmarkReviewProposalDB,
    HumanAIComparisonDB,
    ReviewAuditEventDB,
    ReviewBatchDB,
    ReviewDB,
)
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.evaluation.review_datasets import load_review_dataset_by_id

MAPPING = {"NEEDS_IMPROVEMENT": "NEEDS_REFINEMENT", "NEEDS_REVIEW": "NEEDS_DISCUSSION"}
DATASETS = (("goal-validation", "goal-validation-v1"), ("goal-validation-v1", "1.0.0"))


def _hash(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _audit(
    db: Session, *, batch_id: str, actor_user_id: str, event_type: str,
    entity_id: str, case_record_id: str | None, details: dict, created_at: datetime,
) -> None:
    db.add(ReviewAuditEventDB(
        id=str(uuid4()), batch_id=batch_id, case_record_id=case_record_id,
        event_type=event_type, actor_user_id=actor_user_id,
        entity_id=entity_id, details=details, created_at=created_at,
    ))


def migrate_labels(db: Session, *, actor_user_id: str, apply: bool = False) -> dict:
    actor = db.get(UserDB, actor_user_id)
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise ValueError("An active platform administrator must initiate the migration.")

    summary = {"dry_run": not apply, "datasets": []}
    for dataset_id, dataset_version in DATASETS:
        batch = db.scalar(
            select(ReviewBatchDB).where(
                ReviewBatchDB.dataset_id == dataset_id,
                ReviewBatchDB.dataset_version == dataset_version,
            ).with_for_update()
        )
        if batch is None:
            continue
        catalogue = db.scalar(
            select(BenchmarkDatasetVersionDB).where(
                BenchmarkDatasetVersionDB.dataset_id == dataset_id,
                BenchmarkDatasetVersionDB.dataset_version == dataset_version,
            ).with_for_update()
        )
        if catalogue is None:
            raise ValueError(f"{dataset_id}: registered catalogue is missing.")
        dataset = load_review_dataset_by_id(dataset_id, dataset_version)
        old_dataset = copy.deepcopy(dataset)
        reverse = {value: key for key, value in MAPPING.items()}
        for case in old_dataset["cases"]:
            case["review_label_options"] = [
                reverse.get(label, label) for label in case["review_label_options"]
            ]
        if catalogue.content_hash not in {_hash(old_dataset), _hash(dataset)}:
            raise ValueError(f"{dataset_id}: catalogue content differs from the expected dataset.")
        versions = db.scalars(
            select(BenchmarkCaseVersionDB).where(
                BenchmarkCaseVersionDB.dataset_id == dataset_id,
                BenchmarkCaseVersionDB.dataset_version == dataset_version,
            ).with_for_update()
        ).all()
        expected_cases = {case["case_id"]: case for case in dataset["cases"]}
        old_cases = {case["case_id"]: case for case in old_dataset["cases"]}
        if {case.case_id for case in versions} != set(expected_cases):
            raise ValueError(f"{dataset_id}: catalogue cases do not match the dataset.")
        case_records = {case.case_id: case for case in batch.cases}
        if set(case_records) != set(expected_cases):
            raise ValueError(f"{dataset_id}: batch cases do not match the dataset.")
        comparisons = db.scalar(
            select(HumanAIComparisonDB.id)
            .where(HumanAIComparisonDB.case_record_id.in_([case.id for case in batch.cases]))
            .limit(1)
        )
        if comparisons is not None:
            raise ValueError(f"{dataset_id}: AI comparisons require a separate migration.")

        now = datetime.now(UTC)

        changed_cases = 0
        for version in versions:
            new_case = expected_cases[version.case_id]
            old_case = old_cases[version.case_id]
            if (version.case_json, version.content_hash, version.label_options) not in (
                (old_case, _hash(old_case), old_case["review_label_options"]),
                (new_case, _hash(new_case), new_case["review_label_options"]),
            ):
                raise ValueError(f"{dataset_id}/{version.case_id}: case snapshot has unexpected content.")
            if version.content_hash != _hash(new_case):
                _audit(
                    db, batch_id=batch.id, actor_user_id=actor_user_id,
                    event_type="GOAL_LABEL_CASE_MIGRATED", entity_id=version.id,
                    case_record_id=case_records[version.case_id].id, created_at=now,
                    details={
                        "old_content_hash": version.content_hash, "new_content_hash": _hash(new_case),
                        "old_label_options": version.label_options,
                        "new_label_options": new_case["review_label_options"],
                    },
                )
                version.case_json = new_case
                version.label_options = new_case["review_label_options"]
                version.content_hash = _hash(new_case)
                changed_cases += 1
            for label in new_case["review_label_options"]:
                label_id = hashlib.sha256(f"{version.category}:{label}".encode()).hexdigest()[:64]
                if db.get(BenchmarkLabelDB, label_id) is None:
                    db.add(BenchmarkLabelDB(
                        id=label_id, category_id=version.category, label=label,
                        polarity=None, is_active=True,
                    ))
                    db.flush()
        if catalogue.content_hash != _hash(dataset):
            _audit(
                db, batch_id=batch.id, actor_user_id=actor_user_id,
                event_type="GOAL_LABEL_DATASET_MIGRATED", entity_id=catalogue.id,
                case_record_id=None, created_at=now, details={
                    "old_content_hash": catalogue.content_hash, "new_content_hash": _hash(dataset),
                    "mapping": MAPPING,
                },
            )
            catalogue.content_hash = _hash(dataset)

        reviews = db.scalars(select(ReviewDB).where(
            ReviewDB.dataset_id == dataset_id, ReviewDB.dataset_version == dataset_version,
        ).with_for_update()).all()
        proposals = db.scalars(select(BenchmarkReviewProposalDB).where(
            BenchmarkReviewProposalDB.source_dataset_id == dataset_id,
            BenchmarkReviewProposalDB.source_dataset_version == dataset_version,
        ).with_for_update()).all()
        adjudications = db.scalars(select(AdjudicationDB).where(
            AdjudicationDB.dataset_id == dataset_id,
            AdjudicationDB.dataset_version == dataset_version,
        ).with_for_update()).all()
        version_cases = {case.id: case.case_id for case in versions}
        changed = {"reviews": 0, "proposals": 0, "adjudications": 0}
        for kind, records, attr in (
            ("reviews", reviews, "label"),
            ("proposals", proposals, "proposed_label"),
            ("proposal_references", proposals, "provisional_expected_label"),
            ("adjudications", adjudications, "final_label"),
        ):
            for record in records:
                old_label = getattr(record, attr)
                if old_label is None and kind == "proposal_references":
                    continue
                if old_label not in {"READY", "INVALID", *MAPPING, *MAPPING.values()}:
                    raise ValueError(f"{dataset_id}: unexpected {kind} label {old_label!r}.")
                if old_label in MAPPING:
                    case_id = (
                        version_cases[record.case_version_id]
                        if kind in {"proposals", "proposal_references"} else record.case_id
                    )
                    _audit(
                        db, batch_id=batch.id, actor_user_id=actor_user_id,
                        event_type="GOAL_LABEL_RECORD_MIGRATED", entity_id=record.id,
                        case_record_id=case_records[case_id].id, created_at=now, details={
                            "record_type": kind, "field": attr, "old_label": old_label,
                            "new_label": MAPPING[old_label],
                        },
                    )
                    setattr(record, attr, MAPPING[old_label])
                    changed["proposals" if kind == "proposal_references" else kind] += 1
        summary["datasets"].append({
            "dataset_id": dataset_id, "version": dataset_version, "batch_id": batch.id,
            "case_count": len(versions), "changed_cases": changed_cases,
            "review_count": len(reviews), "proposal_count": len(proposals),
            "adjudication_count": len(adjudications), **changed,
        })
    if apply:
        db.commit()
    else:
        db.rollback()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor-user-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        print(json.dumps(migrate_labels(db, actor_user_id=args.actor_user_id, apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
