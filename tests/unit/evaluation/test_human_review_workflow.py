from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.human_review import (
    AdjudicationDB,
    ReviewAssignmentDB,
    ReviewAuditEventDB,
    ReviewBatchDB,
    ReviewCaseDB,
    ReviewDB,
)
from app.db.models.organization import OrganizationDB
from app.db.models.team import TeamDB
from app.db.models.user import UserDB
from app.services.human_review import (
    M66ReviewError,
    create_review_batch,
    get_case_for_reviewer,
    submit_adjudication,
    submit_review,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        UserDB.__table__,
        OrganizationDB.__table__,
        TeamDB.__table__,
        ReviewBatchDB.__table__,
        ReviewCaseDB.__table__,
        ReviewAssignmentDB.__table__,
        ReviewDB.__table__,
        AdjudicationDB.__table__,
        ReviewAuditEventDB.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session


def _batch(db: Session) -> str:
    return create_review_batch(
        db,
        dataset_id="m66-criterion-assessment",
        dataset_version="v1",
        case_ids=["case-agree", "case-disagree"],
        started_by_user_id="owner",
        assignments={
            "case-agree": ["reviewer-a", "reviewer-b"],
            "case-disagree": ["reviewer-a", "reviewer-b"],
        },
        batch_id="batch-1",
        started_at=datetime(2026, 11, 1, tzinfo=UTC),
    ).id


def test_second_reviewer_cannot_see_first_review_before_submitting(db: Session):
    batch_id = _batch(db)
    submit_review(
        db,
        batch_id=batch_id,
        case_id="case-agree",
        reviewer_user_id="reviewer-a",
        label="MET",
        rationale="The completion evidence directly supports the criterion.",
    )

    view = get_case_for_reviewer(
        db,
        batch_id=batch_id,
        case_id="case-agree",
        reviewer_user_id="reviewer-b",
    )

    assert view["own_review"] is None
    assert view["reviews"] == []


def test_matching_reviews_are_agreed_and_reviews_are_immutable(db: Session):
    batch_id = _batch(db)
    first = submit_review(
        db,
        batch_id=batch_id,
        case_id="case-agree",
        reviewer_user_id="reviewer-a",
        label="MET",
        rationale="The evidence supports completion.",
    )
    submit_review(
        db,
        batch_id=batch_id,
        case_id="case-agree",
        reviewer_user_id="reviewer-b",
        label="MET",
        rationale="The same evidence supports completion.",
    )

    case = db.query(ReviewCaseDB).filter_by(case_id="case-agree").one()
    assert case.status.value == "AGREED"
    with pytest.raises(M66ReviewError, match="cannot submit a case review twice"):
        submit_review(
            db,
            batch_id=batch_id,
            case_id="case-agree",
            reviewer_user_id="reviewer-a",
            label="NEEDS_REVIEW",
            rationale="Attempted amendment.",
        )
    assert db.get(ReviewDB, first.id).rationale == "The evidence supports completion."


def test_disagreement_requires_distinct_adjudicator_and_can_be_resolved(db: Session):
    batch_id = _batch(db)
    submit_review(
        db,
        batch_id=batch_id,
        case_id="case-disagree",
        reviewer_user_id="reviewer-a",
        label="MET",
        rationale="One source supports completion.",
    )
    submit_review(
        db,
        batch_id=batch_id,
        case_id="case-disagree",
        reviewer_user_id="reviewer-b",
        label="NEEDS_REVIEW",
        rationale="A conflicting source prevents a definitive result.",
    )

    with pytest.raises(M66ReviewError, match="distinct from both reviewers"):
        submit_adjudication(
            db,
            batch_id=batch_id,
            case_id="case-disagree",
            adjudicator_user_id="reviewer-a",
            final_label="NEEDS_REVIEW",
            rationale="The conflicting source is material.",
        )

    adjudication = submit_adjudication(
        db,
        batch_id=batch_id,
        case_id="case-disagree",
        adjudicator_user_id="adjudicator",
        final_label="NEEDS_REVIEW",
        rationale="The conflicting source requires a cautious outcome.",
    )
    case = db.query(ReviewCaseDB).filter_by(case_id="case-disagree").one()
    assert case.status.value == "ADJUDICATED"
    assert adjudication.review_1_id != adjudication.review_2_id
    assert db.query(ReviewDB).filter_by(case_record_id=case.id).count() == 2


def test_batch_becomes_human_reviewed_only_after_every_case_is_complete(db: Session):
    batch_id = _batch(db)
    submit_review(
        db,
        batch_id=batch_id,
        case_id="case-agree",
        reviewer_user_id="reviewer-a",
        label="MET",
        rationale="Supported.",
    )
    submit_review(
        db,
        batch_id=batch_id,
        case_id="case-agree",
        reviewer_user_id="reviewer-b",
        label="MET",
        rationale="Supported.",
    )
    batch = db.get(ReviewBatchDB, batch_id)
    assert batch.status.value == "IN_REVIEW"

    for reviewer, label, rationale in [
        ("reviewer-a", "MET", "Supported."),
        ("reviewer-b", "NEEDS_REVIEW", "Conflicting evidence."),
    ]:
        submit_review(
            db,
            batch_id=batch_id,
            case_id="case-disagree",
            reviewer_user_id=reviewer,
            label=label,
            rationale=rationale,
        )
    assert db.get(ReviewBatchDB, batch_id).status.value == "IN_REVIEW"

    submit_adjudication(
        db,
        batch_id=batch_id,
        case_id="case-disagree",
        adjudicator_user_id="adjudicator",
        final_label="NEEDS_REVIEW",
        rationale="Adjudicated from both source-grounded reviews.",
    )
    assert db.get(ReviewBatchDB, batch_id).status.value == "HUMAN_REVIEWED"


def test_single_reviewer_batch_completes_without_second_review_or_adjudication(
    db: Session,
):
    batch_id = create_review_batch(
        db,
        dataset_id="m66-intelligence-comparison",
        dataset_version="v1",
        case_ids=["case-single"],
        started_by_user_id="owner",
        assignments={"case-single": ["reviewer-a"]},
        review_mode="SINGLE_REVIEWER",
        batch_id="single-batch",
        started_at=datetime(2026, 11, 1, tzinfo=UTC),
    ).id

    submit_review(
        db,
        batch_id=batch_id,
        case_id="case-single",
        reviewer_user_id="reviewer-a",
        label="VALID",
        rationale="The goal is specific and connected to a meaningful outcome.",
        allowed_labels={"VALID", "INVALID", "NEEDS_REVIEW"},
    )

    case = db.query(ReviewCaseDB).filter_by(case_id="case-single").one()
    assert case.status.value == "REVIEWED"
    assert db.get(ReviewBatchDB, batch_id).status.value == "HUMAN_REVIEWED"
