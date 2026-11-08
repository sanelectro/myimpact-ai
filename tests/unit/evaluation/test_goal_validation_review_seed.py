import copy
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.v1.human_review import (
    BatchFinalSubmissionRequest,
    ReviewSubmissionRequest,
    get_review_case,
    preview_batch_reviews,
    reviewer_queue,
    save_case_review_draft,
    submit_case_review,
    submit_final_batch_review,
)
from app.auth import AuthenticatedUser
from app.db.base import Base
from app.db.models.human_review import (
    BenchmarkCaseVersionDB,
    BenchmarkDatasetVersionDB,
    BenchmarkReviewProposalDB,
    ReviewAssignmentDB,
    ReviewAuditEventDB,
    ReviewBatchDB,
    ReviewDB,
)
from app.db.models.team import TeamDB
from app.db.models.user import UserDB
from app.evaluation.review_datasets import (
    PROPOSAL_SOURCE_PATH,
    load_proposal_dataset,
    load_review_dataset_by_id,
)
from app.services.human_review import M66ReviewError, submit_review
from scripts.migrate_goal_validation_labels import MAPPING, _hash, migrate_labels
from scripts.seed_goal_validation_proposals import seed_proposals
from scripts.seed_goal_validation_review import seed_review


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    assert TeamDB.__table__.name == "teams"
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        now = datetime.now(UTC)
        for user_id, admin, reviewer in (
            ("admin", True, False),
            ("reviewer-1", False, True),
            ("reviewer-2", False, True),
            ("unassigned-reviewer", False, True),
        ):
            session.add(
                UserDB(
                    id=user_id,
                    name=user_id,
                    email=f"{user_id}@example.test",
                    is_active=True,
                    is_platform_admin=admin,
                    is_reviewer=reviewer,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
        yield session
    engine.dispose()


def _seed(db, apply=True, reviewers=None):
    return seed_review(
        db,
        actor_user_id="admin",
        reviewer_ids=reviewers or ["reviewer-1", "reviewer-2"],
        apply=apply,
    )


def _user(user_id):
    return AuthenticatedUser(
        user_id, f"{user_id}@example.test", None, {"myimpact-ai"}, is_reviewer=True
    )


def test_goal_review_adapter_preserves_inputs_and_hides_provisional_answers():
    dataset = load_review_dataset_by_id("goal-validation", "goal-validation-v1")
    assert len(dataset["cases"]) == 30
    assert len({case["category"] for case in dataset["cases"]}) == 6
    assert dataset["label_status"] == "DRAFT_UNREVIEWED"
    for case in dataset["cases"]:
        assert case["review_kind"] == "GOAL_VALIDATION"
        assert case["reference_visibility"] == "BLIND"
        assert set(case["review_label_options"]) == {
            "READY", "NEEDS_REFINEMENT", "NEEDS_DISCUSSION", "INVALID"
        }
        assert "provisional_reference" not in case
        assert "expected_status" not in case
        assert "criterion" not in case
        assert "evidence" not in case
    with pytest.raises(FileNotFoundError):
        load_review_dataset_by_id("goal-validation", "unknown-version")


def test_dry_run_does_not_create_review_records(db):
    summary = _seed(db, apply=False)
    assert summary["case_count"] == 30
    assert summary["assignments"] == 60
    assert summary["dry_run"] is True
    assert db.scalar(select(func.count()).select_from(ReviewBatchDB)) == 0
    assert db.scalar(select(func.count()).select_from(BenchmarkDatasetVersionDB)) == 0


def test_seed_is_idempotent_with_no_fabricated_decisions(db):
    first = _seed(db)
    second = _seed(db)
    assert first["created"] is True
    assert second["created"] is False
    assert first["batch_id"] == second["batch_id"]
    assert db.scalar(select(func.count()).select_from(BenchmarkCaseVersionDB)) == 30
    assert db.scalar(select(func.count()).select_from(ReviewAssignmentDB)) == 60
    assert db.scalar(select(func.count()).select_from(ReviewDB)) == 0
    dataset = db.scalar(select(BenchmarkDatasetVersionDB))
    assert dataset.status == "DRAFT_UNREVIEWED"
    batch = db.get(ReviewBatchDB, first["batch_id"])
    assert batch.review_mode == "DUAL_ADJUDICATED"
    assert batch.completed_at is None
    with pytest.raises(ValueError, match="different cases or assignments"):
        _seed(db, reviewers=["reviewer-1", "unassigned-reviewer"])


def test_seeded_cases_are_readable_and_accept_goal_readiness_labels(db):
    summary = _seed(db)
    reviewer = _user("reviewer-1")
    queue = reviewer_queue(summary["batch_id"], reviewer, db)
    assert len(queue) == 30
    context = get_review_case(summary["batch_id"], "gv-01", reviewer, db)
    assert context["case"]["goal"]["title"] == "Improve platform quality"
    assert context["reference_proposal"] is None
    assert context["ai_assessment"] is None
    assert context["own_review"] is None
    saved = submit_case_review(
        summary["batch_id"],
        "gv-01",
        ReviewSubmissionRequest(
            label="NEEDS_REFINEMENT",
            rationale="Clarify the quality measure and employee accountability.",
        ),
        reviewer,
        db,
    )
    assert saved.label == "NEEDS_REFINEMENT"
    assert saved.is_final is False
    second_view = get_review_case(
        summary["batch_id"], "gv-01", _user("reviewer-2"), db
    )
    assert second_view["reviews"] == []
    with pytest.raises(HTTPException) as exc:
        get_review_case(summary["batch_id"], "gv-01", _user("unassigned-reviewer"), db)
    assert exc.value.status_code == 403


def test_invalid_reviewer_is_rejected_without_creating_a_batch(db):
    with pytest.raises(ValueError, match="active dedicated reviewer"):
        _seed(db, reviewers=["reviewer-1", "admin"])
    assert db.scalar(select(func.count()).select_from(ReviewBatchDB)) == 0


def _seed_proposals(db, apply=True):
    return seed_proposals(
        db,
        actor_user_id="admin",
        reviewer_ids=["reviewer-1", "reviewer-2"],
        apply=apply,
    )


def test_proposal_dataset_adapter_preserves_source_inputs_and_hides_suggestions():
    source = load_proposal_dataset()
    dataset = load_review_dataset_by_id("goal-validation-v1", "1.0.0")
    assert len(dataset["cases"]) == 30
    for source_case, adapted_case in zip(source.cases, dataset["cases"], strict=True):
        assert adapted_case["case_id"] == source_case.case_id
        assert adapted_case["goal"] == source_case.goal
        assert adapted_case["goal_validation_context"] == source_case.context
        assert adapted_case["case_version"] == source_case.case_version
        assert "ai_suggestion" not in adapted_case
        assert "reference" not in adapted_case
    assert source.cases[0].ai_suggestion.model_reference is None
    assert source.cases[0].ai_suggestion.prompt_version is None


def test_proposal_dry_run_and_idempotent_seed_preserve_existing_batch(db):
    previous = _seed(db)
    db.autoflush = False
    dry_run = _seed_proposals(db, apply=False)
    assert dry_run["proposal_count"] == 30
    assert dry_run["dry_run"] is True
    assert db.scalar(select(func.count()).select_from(BenchmarkReviewProposalDB)) == 0
    first = _seed_proposals(db)
    second = _seed_proposals(db)
    assert first["created"] is True
    assert second["created"] is False
    assert first["batch_id"] == second["batch_id"]
    assert previous["batch_id"] != first["batch_id"]
    assert db.scalar(select(func.count()).select_from(BenchmarkReviewProposalDB)) == 30
    assert db.scalar(select(func.count()).select_from(ReviewDB)) == 0
    assert db.scalar(select(func.count()).select_from(ReviewAssignmentDB)) == 120
    proposals = db.scalars(select(BenchmarkReviewProposalDB)).all()
    assert all(proposal.status == "PROPOSED" for proposal in proposals)
    assert all(proposal.source_document == PROPOSAL_SOURCE_PATH.name for proposal in proposals)
    assert all(proposal.provisional_expected_label is None for proposal in proposals)
    versions = {
        version.id: version
        for version in db.scalars(
            select(BenchmarkCaseVersionDB).where(
                BenchmarkCaseVersionDB.dataset_id == "goal-validation-v1",
                BenchmarkCaseVersionDB.dataset_version == "1.0.0",
            )
        )
    }
    source = {case.case_id: case for case in load_proposal_dataset().cases}
    assert {versions[proposal.case_version_id].case_id for proposal in proposals} == set(source)
    for proposal in proposals:
        version = versions[proposal.case_version_id]
        suggestion = source[version.case_id].ai_suggestion
        assert proposal.proposed_label == suggestion.suggested_label.value
        assert proposal.rationale == suggestion.rationale


def test_proposals_are_visible_before_review_and_recorded_as_assisted(db):
    batch = _seed_proposals(db)
    first = _user("reviewer-1")
    second = _user("reviewer-2")
    case = get_review_case(batch["batch_id"], "gv-04", first, db)
    assert case["case"]["goal"]["accountability"] is None
    proposal = case["reference_proposal"]
    assert proposal.proposed_label == "NEEDS_REFINEMENT"
    assert case["case"]["reference_visibility"] == "PROPOSAL_ASSISTED"
    assert get_review_case(batch["batch_id"], "gv-04", second, db)["reference_proposal"].id == proposal.id
    with pytest.raises(HTTPException) as exc:
        submit_case_review(
            batch["batch_id"], "gv-04",
            ReviewSubmissionRequest(label="NEEDS_REFINEMENT", rationale="Missing proposal reference."),
            first, db,
        )
    assert exc.value.status_code == 409
    saved = save_case_review_draft(
        batch["batch_id"],
        "gv-04",
        ReviewSubmissionRequest(
            label="NEEDS_REFINEMENT", rationale="Clarify acceptance.",
            review_stage="PROPOSAL_ASSISTED", reference_proposal_id=proposal.id,
        ),
        first,
        db,
    )
    assert not saved.is_final
    assert saved.review_stage == "PROPOSAL_ASSISTED"
    assert saved.reference_proposal_id == proposal.id
    with pytest.raises(HTTPException) as exc:
        get_review_case(batch["batch_id"], "gv-04", _user("unassigned-reviewer"), db)
    assert exc.value.status_code == 403
    for source_case in load_proposal_dataset().cases:
        if source_case.case_id != "gv-04":
            proposal_id = get_review_case(
                batch["batch_id"], source_case.case_id, first, db
            )["reference_proposal"].id
            submit_case_review(
                batch["batch_id"],
                source_case.case_id,
                ReviewSubmissionRequest(
                    label="READY", rationale="Human assessment.",
                    review_stage="PROPOSAL_ASSISTED", reference_proposal_id=proposal_id,
                ),
                first,
                db,
            )
    preview = preview_batch_reviews(batch["batch_id"], first, db)
    assert preview["can_finalize"]
    result = submit_final_batch_review(
        batch["batch_id"],
        BatchFinalSubmissionRequest(preview_token=preview["preview_token"]),
        first,
        db,
    )
    assert result == {"is_final": True, "finalized_cases": 30}
    visible = get_review_case(batch["batch_id"], "gv-04", first, db)
    assert visible["reference_proposal"].proposed_label == "NEEDS_REFINEMENT"
    assert visible["reference_proposal"].status == "PROPOSED"
    assert visible["own_review"].review_stage == "PROPOSAL_ASSISTED"
    assert get_review_case(batch["batch_id"], "gv-04", second, db)["reference_proposal"].id == proposal.id
    assert get_review_case(batch["batch_id"], "gv-04", second, db)["reviews"] == []


def test_original_batch_remains_blind_and_proposal_batch_rejects_blind_or_wrong_proposals(db):
    original = _seed(db)
    batch = _seed_proposals(db)
    proposal = get_review_case(batch["batch_id"], "gv-01", _user("reviewer-1"), db)["reference_proposal"]
    wrong_proposal = get_review_case(batch["batch_id"], "gv-02", _user("reviewer-1"), db)["reference_proposal"]
    with pytest.raises(M66ReviewError, match="blind independent"):
        submit_review(
            db,
            batch_id=original["batch_id"],
            case_id="gv-01",
            reviewer_user_id="reviewer-1",
            label="READY",
            rationale="Review.",
            allowed_labels={"READY", "NEEDS_REFINEMENT", "NEEDS_DISCUSSION", "INVALID"},
            review_stage="PROPOSAL_ASSISTED",
            reference_proposal_id=proposal.id,
        )
    with pytest.raises(M66ReviewError, match="requires a proposal-assisted"):
        submit_review(
            db, batch_id=batch["batch_id"], case_id="gv-01", reviewer_user_id="reviewer-1",
            label="READY", rationale="Review.", allowed_labels={"READY"}, review_stage="BLIND",
        )
    with pytest.raises(HTTPException) as exc:
        submit_case_review(
            batch["batch_id"],
            "gv-01",
            ReviewSubmissionRequest(
                label="READY",
                rationale="Review.",
                review_stage="PROPOSAL_ASSISTED",
                reference_proposal_id=wrong_proposal.id,
            ),
            _user("reviewer-1"),
            db,
        )
    assert exc.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(ReviewDB)) == 0


def test_proposal_dataset_rejects_duplicates_and_approved_references(tmp_path):
    import json

    original = json.loads(PROPOSAL_SOURCE_PATH.read_text(encoding="utf-8"))
    original["cases"][1]["case_id"] = original["cases"][0]["case_id"]
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_proposal_dataset(path)
    original["cases"][1]["case_id"] = "gv-02"
    original["cases"][0]["reference"]["approval_status"] = "APPROVED"
    path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="references must be unapproved"):
        load_proposal_dataset(path)


def test_label_migration_preserves_finalized_review_and_is_idempotent(db):
    batch = _seed_proposals(db)
    user = _user("reviewer-1")
    proposal = get_review_case(batch["batch_id"], "gv-04", user, db)["reference_proposal"]
    saved = submit_case_review(
        batch["batch_id"], "gv-04",
        ReviewSubmissionRequest(
            label="NEEDS_REFINEMENT", rationale="Reviewer rationale.",
            review_stage="PROPOSAL_ASSISTED", reference_proposal_id=proposal.id,
        ),
        user, db,
    )
    review = db.get(ReviewDB, saved.id)
    review.is_final = True
    review.label = "NEEDS_IMPROVEMENT"
    original_review_id = review.id
    original_user = review.reviewer_user_id
    dataset = load_review_dataset_by_id("goal-validation-v1", "1.0.0")
    old_dataset = copy.deepcopy(dataset)
    reverse = {value: key for key, value in MAPPING.items()}
    for case in old_dataset["cases"]:
        case["review_label_options"] = [
            reverse.get(label, label) for label in case["review_label_options"]
        ]
    catalogue = db.scalar(select(BenchmarkDatasetVersionDB))
    catalogue.content_hash = _hash(old_dataset)
    versions = db.scalars(select(BenchmarkCaseVersionDB)).all()
    old_cases = {case["case_id"]: case for case in old_dataset["cases"]}
    for version in versions:
        version.case_json = old_cases[version.case_id]
        version.label_options = old_cases[version.case_id]["review_label_options"]
        version.content_hash = _hash(version.case_json)
    for item in db.scalars(select(BenchmarkReviewProposalDB)):
        item.proposed_label = reverse.get(item.proposed_label, item.proposed_label)
    db.commit()
    before_audits = db.scalar(select(func.count()).select_from(ReviewAuditEventDB))

    dry_run = migrate_labels(db, actor_user_id="admin")
    assert dry_run["datasets"][0]["reviews"] == 1
    assert db.get(ReviewDB, original_review_id).label == "NEEDS_IMPROVEMENT"
    assert db.scalar(select(func.count()).select_from(ReviewAuditEventDB)) == before_audits

    result = migrate_labels(db, actor_user_id="admin", apply=True)
    assert result["datasets"][0]["changed_cases"] == 30
    assert result["datasets"][0]["reviews"] == 1
    updated = db.get(ReviewDB, original_review_id)
    assert updated.reviewer_user_id == original_user
    assert updated.rationale == "Reviewer rationale."
    assert updated.is_final
    assert updated.label == "NEEDS_REFINEMENT"
    event = db.scalar(select(ReviewAuditEventDB).where(
        ReviewAuditEventDB.entity_id == original_review_id,
        ReviewAuditEventDB.event_type == "GOAL_LABEL_RECORD_MIGRATED",
    ))
    assert event.details["old_label"] == "NEEDS_IMPROVEMENT"
    assert event.details["new_label"] == "NEEDS_REFINEMENT"
    audit_count = db.scalar(select(func.count()).select_from(ReviewAuditEventDB))
    repeated = migrate_labels(db, actor_user_id="admin", apply=True)
    assert repeated["datasets"][0]["changed_cases"] == 0
    assert repeated["datasets"][0]["reviews"] == 0
    assert repeated["datasets"][0]["proposals"] == 0
    assert db.scalar(select(func.count()).select_from(ReviewAuditEventDB)) == audit_count
    assert _seed_proposals(db)["created"] is False
