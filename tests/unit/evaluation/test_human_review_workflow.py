from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.human_review import (
    BatchFinalSubmissionRequest,
    ReviewSubmissionRequest,
    get_review_case as api_get_review_case,
    save_case_review_draft,
    preview_batch_reviews,
    reviewer_queue,
    submit_final_batch_review,
    submit_case_review as api_submit_case_review,
)
from app.auth import AuthenticatedUser
from app.db.base import Base
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
from app.db.models.organization import OrganizationDB
from app.db.models.team import TeamDB
from app.db.models.user import UserDB
from app.db.models.reliability import ReliabilityAttemptDB, ReliabilityExperimentDB
from app.evaluation.assessment_evaluation import load_dataset_by_id
from app.services.human_review import (
    M66ReviewError,
    PRIMARY_REVIEW_STAGES,
    create_review_batch,
    finalize_batch_reviews,
    get_batch_review_preview,
    get_case_for_reviewer,
    register_benchmark_dataset,
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
        BenchmarkDatasetVersionDB.__table__,
        BenchmarkCategoryDB.__table__,
        BenchmarkLabelDB.__table__,
        BenchmarkReviewProposalDB.__table__,
        BenchmarkDimensionDB.__table__,
        BenchmarkCaseVersionDB.__table__,
        ReviewBatchDB.__table__,
        ReviewCaseDB.__table__,
        ReviewAssignmentDB.__table__,
        ReviewDB.__table__,
        AdjudicationDB.__table__,
        ReviewAuditEventDB.__table__,
        ReliabilityExperimentDB.__table__,
        ReliabilityAttemptDB.__table__,
        HumanAIComparisonDB.__table__,
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
    with pytest.raises(M66ReviewError, match="finalized case review cannot be changed"):
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


def test_proposal_assisted_review_tracks_proposal_and_completes_single_reviewer_batch(
    db: Session,
):
    dataset_id = "m66-intelligence-comparison-v3"
    dataset_version = dataset_id
    dataset = load_dataset_by_id(dataset_id, dataset_version)
    case = dataset["cases"][0]
    case_id = case["case_id"]
    register_benchmark_dataset(
        db,
        dataset=dataset,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        actor_user_id="owner",
    )
    case_version = db.query(BenchmarkCaseVersionDB).filter_by(case_id=case_id).one()
    batch_id = create_review_batch(
        db,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        case_ids=[case_id],
        started_by_user_id="owner",
        assignments={case_id: ["reviewer-a"]},
        review_mode="SINGLE_REVIEWER",
    ).id
    proposal_id = "proposal-for-case-1"
    db.add(
        BenchmarkReviewProposalDB(
            id=proposal_id,
            case_version_id=case_version.id,
            source_document="M6.6-52-Case-Human-Review-Proposal.md",
            source_dataset_id=dataset_id,
            source_dataset_version=dataset_version,
            proposed_label=case["review_label_options"][0],
            provisional_expected_label=None,
            rationale="AI-generated rationale for reviewer consideration.",
            confidence="High",
            evidence_mapping_ids=[],
            review_flags=[],
            requires_owner_attention=False,
            status="PROPOSED",
            created_at=datetime(2026, 11, 8, tzinfo=UTC),
            created_by="model-generated-proposal",
        )
    )
    db.commit()

    reviewer = AuthenticatedUser(
        "reviewer-a", "reviewer-a@example.test", None, {"myimpact-ai"}, is_reviewer=True
    )
    case_response = api_get_review_case(batch_id, case_id, reviewer, db)
    assert case_response["reference_proposal"].rationale == (
        "AI-generated rationale for reviewer consideration."
    )

    with pytest.raises(HTTPException) as exc_info:
        api_submit_case_review(
            batch_id,
            case_id,
            ReviewSubmissionRequest(
                label=case["review_label_options"][0],
                rationale="My review after considering the suggested rationale.",
                review_stage="PROPOSAL_ASSISTED",
                reference_proposal_id="another-case-proposal",
            ),
            reviewer,
            db,
        )
    assert exc_info.value.status_code == 409

    draft = save_case_review_draft(
        batch_id=batch_id,
        case_id=case_id,
        request=ReviewSubmissionRequest(
            label=case["review_label_options"][0],
            rationale="Editable first-pass rationale.",
            review_stage="PROPOSAL_ASSISTED",
            reference_proposal_id=proposal_id,
        ),
        current_user=reviewer,
        db=db,
    )
    assert not draft.is_final
    assert db.get(ReviewBatchDB, batch_id).status.value == "IN_REVIEW"
    case_review_view = api_get_review_case(batch_id, case_id, reviewer, db)
    assert case_review_view["own_review"].id == draft.id
    assert not case_review_view["own_review"].is_final

    review = api_submit_case_review(
        batch_id=batch_id,
        case_id=case_id,
        request=ReviewSubmissionRequest(
            label=case["review_label_options"][0],
            rationale="Final rationale after considering the suggested rationale.",
            review_stage="PROPOSAL_ASSISTED",
            reference_proposal_id=proposal_id,
        ),
        current_user=reviewer,
        db=db,
    )

    assert review.id == draft.id
    assert not review.is_final
    assert db.get(ReviewBatchDB, batch_id).status.value == "IN_REVIEW"
    queue = reviewer_queue(batch_id, reviewer, db)
    assert queue[0].has_draft
    assert not queue[0].submitted_by_current_user
    preview = preview_batch_reviews(batch_id, reviewer, db)
    assert preview["can_finalize"]
    result = submit_final_batch_review(
        batch_id,
        BatchFinalSubmissionRequest(preview_token=preview["preview_token"]),
        reviewer,
        db,
    )
    assert result == {"is_final": True, "finalized_cases": 1}
    assert reviewer_queue(batch_id, reviewer, db)[0].submitted_by_current_user
    assert review.review_stage == "PROPOSAL_ASSISTED"
    assert review.reference_proposal_id == proposal_id
    assert (
        db.query(ReviewDB)
        .filter_by(case_id=case_id, reviewer_user_id="reviewer-a")
        .count()
        == 1
    )
    assert db.get(ReviewBatchDB, batch_id).status.value == "HUMAN_REVIEWED"
    audit_events = db.query(ReviewAuditEventDB).order_by(ReviewAuditEventDB.created_at).all()
    assert any(
        event.event_type == "PROPOSAL_ASSISTED_REVIEW_DRAFT_SAVED"
        for event in audit_events
    )
    edit_event = next(
        event
        for event in audit_events
        if event.details.get("previous_review") is not None
    )
    assert edit_event.details["previous_review"]["rationale"] == (
        "Editable first-pass rationale."
    )
    assert any(
        event.event_type == "REVIEWER_BATCH_FINAL_SUBMITTED"
        and event.details["case_count"] == 1
        for event in audit_events
    )
    reviewer_view = get_case_for_reviewer(
        db,
        batch_id=batch_id,
        case_id=case_id,
        reviewer_user_id="reviewer-a",
        review_stages=PRIMARY_REVIEW_STAGES,
    )
    assert reviewer_view["own_review"].id == review.id


def test_batch_final_submission_requires_every_assigned_case(db: Session):
    batch_id = _batch(db)
    submit_review(
        db, batch_id=batch_id, case_id="case-agree", reviewer_user_id="reviewer-a",
        label="MET", rationale="First saved review.", is_final=False,
    )
    preview = get_batch_review_preview(db, batch_id=batch_id, reviewer_user_id="reviewer-a")
    assert len(preview.cases) == 2
    assert not preview.can_finalize
    with pytest.raises(M66ReviewError, match="every assigned case"):
        finalize_batch_reviews(
            db, batch_id=batch_id, reviewer_user_id="reviewer-a",
            preview_token=preview.preview_token,
        )
    assert not db.query(ReviewDB).one().is_final
    assert db.get(ReviewBatchDB, batch_id).status.value == "IN_REVIEW"
    with pytest.raises(M66ReviewError, match="no assigned cases"):
        get_batch_review_preview(db, batch_id=batch_id, reviewer_user_id="outsider")


def test_complete_batch_remains_editable_and_stale_preview_cannot_finalize(db: Session):
    batch_id = _batch(db)
    for case_id in ["case-agree", "case-disagree"]:
        submit_review(
            db, batch_id=batch_id, case_id=case_id, reviewer_user_id="reviewer-a",
            label="MET", rationale="Initial saved review.", is_final=False,
        )
    first_preview = get_batch_review_preview(db, batch_id=batch_id, reviewer_user_id="reviewer-a")
    assert first_preview.can_finalize
    edited = submit_review(
        db, batch_id=batch_id, case_id="case-agree", reviewer_user_id="reviewer-a",
        label="IN_PROGRESS", rationale="Revised after preview.", is_final=False,
    )
    with pytest.raises(M66ReviewError, match="changed after this preview"):
        finalize_batch_reviews(
            db, batch_id=batch_id, reviewer_user_id="reviewer-a",
            preview_token=first_preview.preview_token,
        )
    assert all(not review.is_final for review in db.query(ReviewDB).all())
    latest = get_batch_review_preview(db, batch_id=batch_id, reviewer_user_id="reviewer-a")
    assert latest.preview_token != first_preview.preview_token
    final = finalize_batch_reviews(
        db, batch_id=batch_id, reviewer_user_id="reviewer-a",
        preview_token=latest.preview_token,
    )
    assert final.is_final
    assert not final.can_finalize
    assert db.get(ReviewDB, edited.id).rationale == "Revised after preview."
    assert db.get(ReviewBatchDB, batch_id).status.value == "IN_REVIEW"
    with pytest.raises(M66ReviewError, match="finalized case review"):
        submit_review(
            db, batch_id=batch_id, case_id="case-agree", reviewer_user_id="reviewer-a",
            label="MET", rationale="Cannot change after final submission.", is_final=False,
        )
    with pytest.raises(M66ReviewError, match="already been submitted"):
        finalize_batch_reviews(
            db, batch_id=batch_id, reviewer_user_id="reviewer-a",
            preview_token=latest.preview_token,
        )
    for case_id in ["case-agree", "case-disagree"]:
        submit_review(
            db, batch_id=batch_id, case_id=case_id, reviewer_user_id="reviewer-b",
            label="IN_PROGRESS", rationale="Second reviewer saved.", is_final=False,
        )
    second = get_batch_review_preview(db, batch_id=batch_id, reviewer_user_id="reviewer-b")
    assert len(second.reviews) == 2
    assert all(review.reviewer_user_id == "reviewer-b" for review in second.reviews)
    finalize_batch_reviews(
        db, batch_id=batch_id, reviewer_user_id="reviewer-b",
        preview_token=second.preview_token,
    )
    assert db.get(ReviewCaseDB, f"{batch_id}:case-agree").status.value == "AGREED"
    assert db.get(ReviewCaseDB, f"{batch_id}:case-disagree").status.value == "DISAGREEMENT"


def test_all_52_case_submissions_are_drafts_until_batch_confirmation(db: Session):
    dataset_id = "m66-intelligence-comparison-v3"
    dataset = load_dataset_by_id(dataset_id, dataset_id)
    cases = dataset["cases"]
    assert len(cases) == 52
    register_benchmark_dataset(
        db, dataset=dataset, dataset_id=dataset_id, dataset_version=dataset_id,
        actor_user_id="owner",
    )
    batch_id = create_review_batch(
        db, dataset_id=dataset_id, dataset_version=dataset_id,
        case_ids=[case["case_id"] for case in cases],
        assignments={case["case_id"]: ["reviewer-a"] for case in cases},
        started_by_user_id="owner", review_mode="SINGLE_REVIEWER",
    ).id
    reviewer = AuthenticatedUser(
        "reviewer-a", "reviewer-a@example.test", None, set(), is_reviewer=True
    )
    for case in cases[:-1]:
        response = api_submit_case_review(
            batch_id, case["case_id"],
            ReviewSubmissionRequest(
                label=case["review_label_options"][0], rationale=f"Review of {case['case_id']}."
            ), reviewer, db,
        )
        assert not response.is_final
    incomplete = preview_batch_reviews(batch_id, reviewer, db)
    assert incomplete["saved_cases"] == 51
    assert not incomplete["can_finalize"]
    with pytest.raises(HTTPException) as error:
        submit_final_batch_review(
            batch_id, BatchFinalSubmissionRequest(preview_token=incomplete["preview_token"]),
            reviewer, db,
        )
    assert error.value.status_code == 409
    last_case = cases[-1]
    api_submit_case_review(
        batch_id, last_case["case_id"],
        ReviewSubmissionRequest(
            label=last_case["review_label_options"][0], rationale="Last case saved."
        ), reviewer, db,
    )
    preview = preview_batch_reviews(batch_id, reviewer, db)
    assert preview["saved_cases"] == preview["total_cases"] == 52
    assert len(preview["reviews"]) == 52
    assert preview["can_finalize"]
    assert db.get(ReviewBatchDB, batch_id).status.value == "IN_REVIEW"
    result = submit_final_batch_review(
        batch_id, BatchFinalSubmissionRequest(preview_token=preview["preview_token"]),
        reviewer, db,
    )
    assert result == {"is_final": True, "finalized_cases": 52}
    assert db.get(ReviewBatchDB, batch_id).status.value == "HUMAN_REVIEWED"
    assert all(review.is_final for review in db.query(ReviewDB).all())
    with pytest.raises(HTTPException) as error:
        api_submit_case_review(
            batch_id, last_case["case_id"],
            ReviewSubmissionRequest(label=last_case["review_label_options"][0], rationale="Locked."),
            reviewer, db,
        )
    assert error.value.status_code == 409


def test_preview_token_changes_when_registered_case_context_changes(db: Session):
    dataset_id = "m66-intelligence-comparison-v3"
    dataset = load_dataset_by_id(dataset_id, dataset_id)
    case = dataset["cases"][0]
    register_benchmark_dataset(
        db, dataset=dataset, dataset_id=dataset_id, dataset_version=dataset_id,
        actor_user_id="owner",
    )
    batch_id = create_review_batch(
        db, dataset_id=dataset_id, dataset_version=dataset_id,
        case_ids=[case["case_id"]], assignments={case["case_id"]: ["reviewer-a"]},
        started_by_user_id="owner", review_mode="SINGLE_REVIEWER",
    ).id
    submit_review(
        db, batch_id=batch_id, case_id=case["case_id"], reviewer_user_id="reviewer-a",
        label=case["review_label_options"][0], rationale="Saved before context correction.",
        is_final=False,
    )
    initial = get_batch_review_preview(db, batch_id=batch_id, reviewer_user_id="reviewer-a")
    case_version = db.query(BenchmarkCaseVersionDB).filter_by(case_id=case["case_id"]).one()
    case_version.content_hash = "f" * 64
    db.commit()
    refreshed = get_batch_review_preview(db, batch_id=batch_id, reviewer_user_id="reviewer-a")
    assert refreshed.preview_token != initial.preview_token
    with pytest.raises(M66ReviewError, match="changed after this preview"):
        finalize_batch_reviews(
            db, batch_id=batch_id, reviewer_user_id="reviewer-a",
            preview_token=initial.preview_token,
        )
    assert not db.query(ReviewDB).one().is_final


def test_dataset_registration_pins_case_versions_and_keeps_labels_draft(db: Session):
    dataset_id = "m66-intelligence-comparison-v4"
    dataset_version = "m66-intelligence-comparison-v4"
    dataset = load_dataset_by_id(dataset_id, dataset_version)
    record = register_benchmark_dataset(
        db,
        dataset=dataset,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        actor_user_id="owner",
    )
    case = dataset["cases"][0]
    batch = create_review_batch(
        db,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        case_ids=[case["case_id"]],
        started_by_user_id="owner",
        assignments={case["case_id"]: ["reviewer-a"]},
        review_mode="SINGLE_REVIEWER",
    )

    assert record.case_count == 52
    assert record.status == "DRAFT_UNREVIEWED"
    assert batch.cases[0].case_version_id is not None
    assert batch.cases[0].category == case["category"]
    stored_case = db.query(BenchmarkCaseVersionDB).filter_by(case_id=case["case_id"]).one()
    assert stored_case.dimensions == case["benchmark_dimensions"]


def test_post_ai_review_references_exact_successful_attempt(db: Session):
    dataset_id = "m66-intelligence-comparison-v4"
    dataset_version = "m66-intelligence-comparison-v4"
    dataset = load_dataset_by_id(dataset_id, dataset_version)
    case = dataset["cases"][0]
    case_id = case["case_id"]
    labels = case["review_label_options"]
    blind_label = labels[0]
    post_ai_label = labels[1]
    register_benchmark_dataset(
        db,
        dataset=dataset,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        actor_user_id="owner",
    )
    batch_id = create_review_batch(
        db,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        case_ids=[case_id],
        started_by_user_id="owner",
        assignments={case_id: ["reviewer-a"]},
        review_mode="SINGLE_REVIEWER",
    ).id
    now = datetime.now(UTC)
    db.add(
        ReliabilityExperimentDB(
            id="experiment-1",
            name="review comparison",
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            case_selection=[case_id],
            prompt_version="prompt-v1",
            model_identifier="fixture-model",
            model_configuration={},
            retrieval_configuration_version="retrieval-v1",
            evaluation_code_version="test",
            output_schema_version="schema-v1",
            normalization_version="normalization-v1",
            repetitions_per_case=1,
            execution_policy={},
            status="COMPLETED",
            created_by_user_id="owner",
            created_at=now,
            started_at=now,
            finished_at=now,
        )
    )
    db.add(
        ReliabilityAttemptDB(
            id="attempt-1",
            experiment_id="experiment-1",
            case_id=case_id,
            sequence=1,
            dataset_version=dataset_version,
            prompt_version="prompt-v1",
            model_identifier="fixture-model",
            retrieval_configuration_version="retrieval-v1",
            input_fingerprint="fingerprint",
            raw_output={},
            normalized_output={"assessment_label": blind_label},
            schema_valid=True,
            status="SUCCEEDED",
            started_at=now,
            finished_at=now,
        )
    )
    db.commit()

    with pytest.raises(M66ReviewError, match="Finalize your primary review"):
        submit_review(
            db,
            batch_id=batch_id,
            case_id=case_id,
            reviewer_user_id="reviewer-a",
            label=blind_label,
            rationale="Before AI.",
            review_stage="POST_AI",
            ai_attempt_id="attempt-1",
            allowed_labels=labels,
        )

    blind_review = submit_review(
        db,
        batch_id=batch_id,
        case_id=case_id,
        reviewer_user_id="reviewer-a",
        label=blind_label,
        rationale="Independent decision before seeing AI.",
        allowed_labels=labels,
    )
    post_ai_review = submit_review(
        db,
        batch_id=batch_id,
        case_id=case_id,
        reviewer_user_id="reviewer-a",
        label=post_ai_label,
        rationale="Decision after seeing the AI result.",
        review_stage="POST_AI",
        ai_attempt_id="attempt-1",
        confidence=0.9,
        allowed_labels=labels,
    )

    comparison = db.query(HumanAIComparisonDB).one()
    assert post_ai_review.ai_attempt_id == "attempt-1"
    assert post_ai_review.confidence == 0.9
    assert comparison.blind_review_id == blind_review.id
    assert comparison.post_ai_review_id == post_ai_review.id
    assert comparison.ai_attempt_id == "attempt-1"
    assert comparison.agreement is True
    assert comparison.comparison_json["post_ai_ai_agreement"] is False
