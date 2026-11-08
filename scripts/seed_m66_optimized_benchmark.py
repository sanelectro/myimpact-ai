"""Seed the draft M6.6 optimized benchmark into the local application database."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.db.base import Base
from app.db.models import (
    AssessmentCategoryDB,
    ReliabilityExperimentDB,
    UserDB,
)
from app.db.session import engine, SessionLocal
from app.evaluation.assessment_evaluation import load_dataset_by_id
from app.services.human_review import create_review_batch

DATASET_ID = "m66-intelligence-comparison-v3"
DATASET_VERSION = DATASET_ID
PROMPT_VERSION = "m66-category-assessment-v1"
NORMALIZATION_VERSION = "m66-reliability-normalization-v1"


def _category_name(category: str) -> str:
    return category.replace("_", " ").strip().title()


def seed(*, skip_experiment: bool = False) -> dict[str, int]:
    dataset = load_dataset_by_id(DATASET_ID, DATASET_VERSION)
    cases = dataset["cases"]

    Base.metadata.create_all(
        bind=engine,
        tables=[AssessmentCategoryDB.__table__],
    )
    now = datetime.now(UTC)
    categories_created = 0
    criteria_added = 0

    with SessionLocal() as db:
        for category in sorted({case["category"] for case in cases}):
            category_row = db.scalar(
                select(AssessmentCategoryDB).where(
                    AssessmentCategoryDB.normalized_name == category.casefold()
                )
            )
            if category_row is None:
                category_row = AssessmentCategoryDB(
                    id=str(uuid4()),
                    name=_category_name(category),
                    normalized_name=category.casefold(),
                    description=(
                        f"Provisional M6.6 benchmark category for {category.replace('_', ' ')}."
                    ),
                    criteria=[],
                    is_active=True,
                    created_by_user_id="m66-seed",
                    created_at=now,
                    updated_at=now,
                )
                db.add(category_row)
                db.flush()
                categories_created += 1

            existing_case_ids = {
                item.get("source_case_id")
                for item in category_row.criteria
                if isinstance(item, dict)
            }
            additions = []
            for case in cases:
                if case["category"] != category or case["case_id"] in existing_case_ids:
                    continue
                additions.append(
                    {
                        "id": str(uuid4()),
                        "source_case_id": case["case_id"],
                        "title": case["assessment_question"],
                        "definition": case["criterion"]["definition"],
                        "provisional": True,
                        "created_at": now.isoformat(),
                        "created_by_user_id": "m66-seed",
                    }
                )
            if additions:
                category_row.criteria = [*category_row.criteria, *additions]
                category_row.updated_at = now
                criteria_added += len(additions)

        admin = db.scalar(
            select(UserDB)
            .where(UserDB.is_platform_admin.is_(True), UserDB.is_active.is_(True))
            .order_by(UserDB.email)
        )
        reviewer = db.scalar(
            select(UserDB)
            .where(UserDB.is_reviewer.is_(True), UserDB.is_active.is_(True))
            .order_by(UserDB.email)
        )
        if admin is None:
            raise RuntimeError("Cannot seed M6.6: no active platform administrator exists.")
        if reviewer is None:
            raise RuntimeError("Cannot seed M6.6: no active evaluation reviewer exists.")

        review_batch_count = 0
        existing_batch = db.execute(
            select(Base.metadata.tables["review_batches"]).where(
                Base.metadata.tables["review_batches"].c.dataset_id == DATASET_ID,
                Base.metadata.tables["review_batches"].c.dataset_version
                == DATASET_VERSION,
            )
        ).first()
        if existing_batch is None:
            create_review_batch(
                db,
                dataset_id=DATASET_ID,
                dataset_version=DATASET_VERSION,
                case_ids=[case["case_id"] for case in cases],
                started_by_user_id=admin.id,
                assignments={case["case_id"]: [reviewer.id] for case in cases},
                review_mode="SINGLE_REVIEWER",
            )
            review_batch_count = 1

        experiment_count = 0
        if not skip_experiment:
            existing_experiment = db.scalar(
                select(ReliabilityExperimentDB).where(
                    ReliabilityExperimentDB.dataset_id == DATASET_ID,
                    ReliabilityExperimentDB.dataset_version == DATASET_VERSION,
                    ReliabilityExperimentDB.status.in_(("DRAFT", "PENDING")),
                )
            )
            if existing_experiment is None:
                db.add(
                    ReliabilityExperimentDB(
                        id=str(uuid4()),
                        name="M6.6.6 Optimized 52-case benchmark",
                        dataset_id=DATASET_ID,
                        dataset_version=DATASET_VERSION,
                        case_selection=[case["case_id"] for case in cases],
                        prompt_version=PROMPT_VERSION,
                        model_identifier="openai/gpt-oss-20b",
                        model_configuration={"temperature": 0},
                        retrieval_configuration_version="retrieval-v1",
                        source_snapshot_id=None,
                        evaluation_code_version="m66.6.6",
                        output_schema_version="assessment-v1",
                        normalization_version=NORMALIZATION_VERSION,
                        repetitions_per_case=3,
                        execution_policy={"max_retries": 2},
                        status="DRAFT",
                        created_by_user_id=admin.id,
                        created_at=now,
                    )
                )
                experiment_count = 1

        db.commit()
        return {
            "categories_created": categories_created,
            "criteria_added": criteria_added,
            "review_batches_created": review_batch_count,
            "experiments_created": experiment_count,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-experiment",
        action="store_true",
        help="Seed categories and review batch without creating the pending experiment.",
    )
    args = parser.parse_args()
    result = seed(skip_experiment=args.skip_experiment)
    for key, value in result.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
