import asyncio
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import app.db.models
from app.db.models.team import TeamDB as _TeamDB
from app.db.models.user import UserDB
from app.models.goal import GoalStatus, GoalSubStatus
from app.models.goal_criteria import (
    GoalCriterionCreateRequest,
    GoalCriterionDefinition,
    GoalCriterionType,
    GoalCriterionUpdateRequest,
)
from app.models.llm import LLMResponse
from app.models.milestone import MilestoneCreate
from app.repositories.goal import GoalRepository
from app.services.goal import GoalService
from app.services.goal_criteria import GoalCriteriaGenerationConflict, GoalCriteriaService
from app.services.goal_definition_proposals import (
    GoalDefinitionProposalService,
    GoalProposalConflict,
    GoalProposalTextChanges,
)
from app.services.goal_validation_runs import GoalValidationRunService
from app.services.milestone import MilestoneService


@pytest.fixture
def goal_version_engine():
    _ = _TeamDB
    container = os.environ.get("GOAL_VERSION_TEST_CONTAINER")
    url = os.environ.get("GOAL_VERSION_TEST_DATABASE_URL")
    if not container and not url:
        pytest.skip("Requires an explicitly configured disposable goal-version database")
    if not container or not url:
        raise RuntimeError("Both disposable container and database URL must be configured")

    label = subprocess.run(
        ["docker", "inspect", "--format", '{{index .Config.Labels "myimpact.test"}}', container],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    port = subprocess.run(
        ["docker", "port", container, "5432/tcp"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    parsed = urlparse(url)
    if (
        label != "phase1-disposable"
        or parsed.scheme != "postgresql+psycopg"
        or parsed.hostname != "127.0.0.1"
        or port != f"127.0.0.1:{parsed.port}"
        or parsed.path != "/hierarchytest"
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("The test database must be the labelled disposable container")

    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


def _create_committed_goal(engine):
    owner_id = f"phase1-owner-{uuid4().hex}"
    goal_id = f"phase1-goal-{uuid4().hex}"
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(UserDB(
            id=owner_id,
            name="Owner",
            email=f"{owner_id}@example.test",
            created_at=now,
            updated_at=now,
        ))
        session.flush()
        GoalRepository(session).create(goal_id=goal_id, user_id=owner_id, title="Original goal")
        session.commit()
    return owner_id, goal_id


def _create_selected_baseline(engine):
    owner_id, goal_id = _create_committed_goal(engine)
    with Session(engine) as session:
        goal = GoalRepository(session).get_by_id(goal_id)
        base_id = GoalRepository(session).get_latest_version(goal_id).id
        goal.operative_goal_version_id = base_id
        goal.status = GoalStatus.ACTIVE
        goal.sub_status = GoalSubStatus.ON_TRACK
        session.commit()
    return owner_id, goal_id, base_id


def _stage_text(session, owner_id, goal_id, base_id, *, key, revision=0, title="Revised goal"):
    return GoalDefinitionProposalService(session).stage_text_proposal(
        goal_id=goal_id,
        actor_user_id=owner_id,
        idempotency_key=key,
        expected_base_version_id=base_id,
        expected_proposal_revision=revision,
        expected_relationship_revision=0,
        changes=GoalProposalTextChanges(title=title),
    )


@pytest.mark.integration
def test_text_proposal_is_isolated_and_retry_returns_original_receipt(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        first = _stage_text(session, owner_id, goal_id, base_id, key="first")
        session.commit()
        second = _stage_text(session, owner_id, goal_id, base_id, key="second", revision=1)
        assert second.outcome == "NO_CHANGE"
        session.commit()
        third = _stage_text(
            session, owner_id, goal_id, base_id, key="third", revision=1, title="Another goal"
        )
        session.commit()
        retry = _stage_text(session, owner_id, goal_id, base_id, key="first")
        assert retry == first
        assert first.outcome == "CREATED"
        assert first.revision == 1
        assert third.revision == 2
        assert third.version_id != first.version_id
        with pytest.raises(GoalProposalConflict, match="different request"):
            _stage_text(session, owner_id, goal_id, base_id, key="first", title="Different")
        session.rollback()

    with Session(goal_version_engine) as session:
        repository = GoalRepository(session)
        goal = repository.get_by_id(goal_id)
        assert goal.title == "Original goal"
        assert goal.status == GoalStatus.ACTIVE
        assert goal.operative_goal_version_id == base_id
        assert repository.get_latest_version(goal_id).id == base_id
        assert session.get(app.db.models.GoalVersionDB, first.version_id).content["title"] == "Revised goal"
        assert session.get(app.db.models.GoalVersionDB, third.version_id).content["title"] == "Another goal"
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id).revision == 2
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalCommandReceiptDB)
            .where(app.db.models.GoalCommandReceiptDB.goal_id == goal_id)
        ) == 3


@pytest.mark.integration
def test_text_proposal_noop_and_rollback_do_not_create_versions(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        noop = _stage_text(
            session, owner_id, goal_id, base_id, key="noop", title="  Original   goal  "
        )
        assert (noop.outcome, noop.revision, noop.version_id) == ("NO_CHANGE", 0, base_id)
        session.commit()
        created = _stage_text(session, owner_id, goal_id, base_id, key="rollback")
        assert created.outcome == "CREATED"
        session.rollback()

    with Session(goal_version_engine) as session:
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None
        assert session.get(app.db.models.GoalVersionDB, created.version_id) is None
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "rollback")
        ) is None
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "noop")
        ) is not None


@pytest.mark.integration
def test_text_proposal_rechecks_owner_revisions_and_live_baseline(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        with pytest.raises(ValueError, match="Goal not found"):
            _stage_text(session, "another-user", goal_id, base_id, key="other")
        session.rollback()
        with pytest.raises(GoalProposalConflict, match="proposal changed"):
            _stage_text(session, owner_id, goal_id, base_id, key="stale", revision=1)
        session.rollback()
        with pytest.raises(GoalProposalConflict, match="definition changed"):
            _stage_text(session, owner_id, goal_id, "different-base", key="wrong-base")
        session.rollback()
        MilestoneService(session).create_milestone(goal_id, MilestoneCreate(title="New milestone"))
        with pytest.raises(GoalProposalConflict, match="no longer matches"):
            _stage_text(session, owner_id, goal_id, base_id, key="changed-baseline")
        session.rollback()
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None


@pytest.mark.integration
@pytest.mark.parametrize("status", [GoalStatus.DRAFT, GoalStatus.COMPLETED, GoalStatus.ARCHIVED])
def test_text_proposal_rejects_nonongoing_lifecycle(goal_version_engine, status):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        goal = GoalRepository(session).get_by_id(goal_id)
        goal.status = status
        session.commit()
        with pytest.raises(GoalProposalConflict, match="approved or active"):
            _stage_text(session, owner_id, goal_id, base_id, key="nonongoing")
        session.rollback()
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None


@pytest.mark.integration
def test_text_proposal_requires_selected_baseline_and_relationship_revision(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        goal = GoalRepository(session).get_by_id(goal_id)
        goal.operative_goal_version_id = None
        session.commit()
        with pytest.raises(GoalProposalConflict, match="not selected"):
            _stage_text(session, owner_id, goal_id, base_id, key="no-baseline")
        session.rollback()
        goal.operative_goal_version_id = base_id
        session.commit()
        with pytest.raises(GoalProposalConflict, match="relationship changed"):
            GoalDefinitionProposalService(session).stage_text_proposal(
                goal_id=goal_id,
                actor_user_id=owner_id,
                idempotency_key="relationship",
                expected_base_version_id=base_id,
                expected_proposal_revision=0,
                expected_relationship_revision=1,
                changes=GoalProposalTextChanges(title="Revised goal"),
            )
        session.rollback()
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None


@pytest.mark.integration
def test_concurrent_text_proposal_retry_serializes_on_idempotency_key(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    attempted = Event()
    with Session(goal_version_engine) as first:
        original = _stage_text(first, owner_id, goal_id, base_id, key="same")

        def retry():
            with Session(goal_version_engine) as second:
                @event.listens_for(second.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "pg_advisory_xact_lock" in statement:
                        attempted.set()

                result = _stage_text(second, owner_id, goal_id, base_id, key="same")
                second.commit()
                return result

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(retry)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                first.commit()
                assert pending.result(timeout=10) == original
            finally:
                first.rollback()
    with Session(goal_version_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalVersionDB)
            .where(app.db.models.GoalVersionDB.goal_id == goal_id)
        ) == 2
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalCommandReceiptDB)
            .where(app.db.models.GoalCommandReceiptDB.goal_id == goal_id)
        ) == 1


@pytest.mark.integration
def test_concurrent_distinct_proposals_recheck_head_revision(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    attempted = Event()
    with Session(goal_version_engine) as first:
        original = _stage_text(first, owner_id, goal_id, base_id, key="first")

        def competing():
            with Session(goal_version_engine) as second:
                @event.listens_for(second.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        attempted.set()

                with pytest.raises(GoalProposalConflict, match="proposal changed"):
                    _stage_text(second, owner_id, goal_id, base_id, key="second", title="Competing")

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(competing)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                first.commit()
                pending.result(timeout=10)
            finally:
                first.rollback()
    with Session(goal_version_engine) as session:
        head = session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id)
        assert head.proposal_version_id == original.version_id
        assert head.revision == 1
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "second")
        ) is None


@pytest.mark.integration
def test_proposal_storage_enforces_same_goal_and_immutable_receipts(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    _, _, other_base = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="stored")
        session.commit()
        for statement, params in [
            (
                "UPDATE goal_definition_proposal_heads SET base_version_id = :version WHERE goal_id = :goal",
                {"version": other_base, "goal": goal_id},
            ),
            (
                "UPDATE goal_definition_proposal_heads SET proposal_version_id = :version WHERE goal_id = :goal",
                {"version": base_id, "goal": goal_id},
            ),
            (
                "UPDATE goal_command_receipts SET result_revision = 99 WHERE goal_id = :goal",
                {"goal": goal_id},
            ),
            (
                "DELETE FROM goal_command_receipts WHERE goal_id = :goal",
                {"goal": goal_id},
            ),
        ]:
            with pytest.raises(DBAPIError):
                with session.begin_nested():
                    session.execute(text(statement), params)

        head = session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id)
        assert head.base_version_id == base_id
        assert head.proposal_version_id == proposal.version_id
        assert GoalRepository(session).delete(goal_id)
        session.commit()
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "stored")
        ) is None


@pytest.mark.integration
@pytest.mark.parametrize(
    "concurrent_change", [None, "proposal", "goal", "criterion", "milestone", "status"]
)
def test_prepared_proposal_validation_rechecks_exact_context_after_provider(
    goal_version_engine, concurrent_change
):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="validate")
        session.commit()

    class ChangingLLM:
        async def generate(self, _request):
            with Session(goal_version_engine) as writer:
                if concurrent_change == "proposal":
                    _stage_text(
                        writer, owner_id, goal_id, base_id,
                        key="newer", revision=1, title="Newer proposal",
                    )
                    writer.commit()
                elif concurrent_change == "goal":
                    GoalService(writer).update_goal(
                        goal_id, {"title": "Changed baseline"}, changed_by_user_id=owner_id
                    )
                elif concurrent_change == "criterion":
                    GoalCriteriaService(writer).create_manual(
                        goal_id,
                        owner_id,
                        GoalCriterionCreateRequest(
                            definition=GoalCriterionDefinition(
                                criterion_type=GoalCriterionType.BINARY,
                                description="A new criterion",
                                completion_conditions="The outcome is verified.",
                            )
                        ),
                    )
                elif concurrent_change == "milestone":
                    MilestoneService(writer).create_milestone(
                        goal_id, MilestoneCreate(title="New milestone")
                    )
                elif concurrent_change == "status":
                    GoalService(writer).transition_status(
                        goal_id, GoalStatus.ARCHIVED, reason="Priorities changed",
                        changed_by_user_id=owner_id,
                    )
            return LLMResponse(
                content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
            )

    with Session(goal_version_engine) as session:
        validator = GoalValidationRunService(session, ChangingLLM())
        if concurrent_change is None:
            run = asyncio.run(
                validator.validate_prepared_proposal(goal_id, proposal.version_id, owner_id)
            )
            assert run.goal_version_id == proposal.version_id
        else:
            with pytest.raises(GoalProposalConflict, match="changed during validation"):
                asyncio.run(
                    validator.validate_prepared_proposal(goal_id, proposal.version_id, owner_id)
                )

    with Session(goal_version_engine) as session:
        runs = session.scalars(
            select(app.db.models.GoalValidationRunDB).where(
                app.db.models.GoalValidationRunDB.goal_version_id == proposal.version_id
            )
        ).all()
        assert len(runs) == 1
        assert runs[0].goal_version_id == proposal.version_id


@pytest.mark.integration
def test_prepared_proposal_validation_rejects_stale_or_unauthorized_before_provider(
    goal_version_engine
):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        first = _stage_text(session, owner_id, goal_id, base_id, key="first")
        session.commit()
        _stage_text(session, owner_id, goal_id, base_id, key="second", revision=1, title="Newer")
        session.commit()

    class UnexpectedLLM:
        async def generate(self, _request):
            pytest.fail("The provider must not run for stale or unauthorized requests")

    with Session(goal_version_engine) as session:
        validator = GoalValidationRunService(session, UnexpectedLLM())
        with pytest.raises(ValueError, match="not found"):
            asyncio.run(validator.validate_prepared_proposal(goal_id, first.version_id, "other"))
        with pytest.raises(GoalProposalConflict, match="superseded"):
            asyncio.run(validator.validate_prepared_proposal(goal_id, first.version_id, owner_id))
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalValidationRunDB)
            .where(app.db.models.GoalValidationRunDB.goal_id == goal_id)
        ) == 0


@pytest.mark.integration
def test_baseline_comparison_preserves_selected_criterion_with_pending_edit(goal_version_engine):
    owner_id, goal_id = _create_committed_goal(goal_version_engine)
    original = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Deploy the release",
        completion_conditions="The release is available.",
    )
    revised = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Deploy the revised release",
        completion_conditions="The revised release is available.",
    )
    with Session(goal_version_engine) as session:
        service = GoalCriteriaService(session)
        criterion = service.create_manual(
            goal_id, owner_id, GoalCriterionCreateRequest(definition=original)
        )
        service.approve_version(goal_id, criterion.id, criterion.versions[0].id, owner_id)
        repository = GoalRepository(session)
        approved_id = repository.get_latest_version(goal_id).id
        service.add_version(
            goal_id, criterion.id, owner_id, GoalCriterionUpdateRequest(definition=revised)
        )
        newest_id = repository.get_latest_version(goal_id).id

    with Session(goal_version_engine) as session:
        repository = GoalRepository(session)
        goal = repository.get_by_id(goal_id)
        approved = session.get(app.db.models.GoalVersionDB, approved_id)
        newest = session.get(app.db.models.GoalVersionDB, newest_id)
        assert repository.compare_live_definition(goal, approved.content) == []
        assert repository.compare_live_definition(goal, newest.content) == ["criterion_versions"]
        assert goal.operative_goal_version_id is None


@pytest.mark.integration
def test_concurrent_lifecycle_transition_rechecks_locked_status(goal_version_engine):
    owner_id, goal_id = _create_committed_goal(goal_version_engine)
    lock_attempted = Event()
    with Session(goal_version_engine) as first:
        assert GoalRepository(first).get_by_id_for_update(goal_id) is not None

        def transition_second():
            with Session(goal_version_engine) as session:
                @event.listens_for(session.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        lock_attempted.set()

                with pytest.raises(ValueError, match="Invalid goal status transition"):
                    GoalService(session).transition_status(
                        goal_id, GoalStatus.ARCHIVED, reason="Second request",
                        changed_by_user_id=owner_id,
                    )

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(transition_second)
            try:
                assert lock_attempted.wait(10)
                assert not pending.done()
                GoalService(first).transition_status(
                    goal_id, GoalStatus.ARCHIVED, reason="First request",
                    changed_by_user_id=owner_id,
                )
                pending.result(timeout=10)
            finally:
                first.rollback()

    with Session(goal_version_engine) as session:
        assert GoalRepository(session).get_by_id(goal_id).status == GoalStatus.ARCHIVED
        history = GoalRepository(session).get_status_history(goal_id)
        assert len(history) == 1
        assert history[0].reason == "First request"


@pytest.mark.integration
def test_criterion_creation_waits_for_goal_writer(goal_version_engine):
    owner_id, goal_id = _create_committed_goal(goal_version_engine)
    lock_attempted = Event()
    request = GoalCriterionCreateRequest(
        definition=GoalCriterionDefinition(
            criterion_type=GoalCriterionType.BINARY,
            description="Deploy the release",
            completion_conditions="The release is available.",
        )
    )
    with Session(goal_version_engine) as first:
        assert GoalRepository(first).get_by_id_for_update(goal_id) is not None

        def create_criterion():
            with Session(goal_version_engine) as session:
                @event.listens_for(session.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        lock_attempted.set()

                return GoalCriteriaService(session).create_manual(goal_id, owner_id, request).id

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(create_criterion)
            try:
                assert lock_attempted.wait(10)
                assert not pending.done()
                with Session(goal_version_engine) as verification:
                    assert GoalCriteriaService(verification).list_for_goal(goal_id) == []
                first.commit()
                criterion_id = pending.result(timeout=10)
            finally:
                first.rollback()

    with Session(goal_version_engine) as verification:
        snapshot = GoalRepository(verification).get_latest_version(goal_id)
        assert snapshot.version == 2
        assert snapshot.content["criterion_versions"][0]["criterion_id"] == criterion_id


@pytest.mark.integration
def test_milestone_creation_waits_for_goal_writer(goal_version_engine):
    _, goal_id = _create_committed_goal(goal_version_engine)
    lock_attempted = Event()
    with Session(goal_version_engine) as first:
        assert GoalRepository(first).get_by_id_for_update(goal_id) is not None

        def create_milestone():
            with Session(goal_version_engine) as session:
                @event.listens_for(session.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        lock_attempted.set()

                return MilestoneService(session).create_milestone(
                    goal_id, MilestoneCreate(title="Deploy the release")
                ).id

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(create_milestone)
            try:
                assert lock_attempted.wait(10)
                assert not pending.done()
                with Session(goal_version_engine) as verification:
                    assert MilestoneService(verification).get_milestones_by_goal_id(goal_id) == []
                first.commit()
                milestone_id = pending.result(timeout=10)
            finally:
                first.rollback()
    with Session(goal_version_engine) as verification:
        assert MilestoneService(verification).get_milestone_by_id_and_goal(
            milestone_id, goal_id
        ).title == "Deploy the release"


@pytest.mark.integration
def test_milestone_writer_rechecks_preloaded_archived_state(goal_version_engine):
    _, goal_id = _create_committed_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        milestone_id = MilestoneService(session).create_milestone(
            goal_id, MilestoneCreate(title="Deploy the release")
        ).id

    lock_attempted = Event()
    with Session(goal_version_engine) as first:
        assert GoalRepository(first).get_by_id_for_update(goal_id) is not None

        def update_milestone():
            with Session(goal_version_engine) as session:
                service = MilestoneService(session)
                stale = service.get_milestone_by_id_and_goal(milestone_id, goal_id)
                assert stale.archived_at is None

                @event.listens_for(session.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        lock_attempted.set()

                with pytest.raises(ValueError, match="Milestone not found"):
                    service.update_milestone(goal_id, milestone_id, {"title": "Stale edit"})

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(update_milestone)
            try:
                assert lock_attempted.wait(10)
                assert not pending.done()
                MilestoneService(first).archive_milestone(goal_id, milestone_id)
                pending.result(timeout=10)
            finally:
                first.rollback()
    with Session(goal_version_engine) as verification:
        milestone = MilestoneService(verification).get_milestone_by_id_and_goal(
            milestone_id, goal_id
        )
        assert milestone.archived_at is not None
        assert milestone.title == "Deploy the release"


@pytest.mark.integration
@pytest.mark.parametrize("concurrent_change", ["goal", "criterion", "status"])
def test_generated_criteria_reject_goal_changed_during_provider_call(
    goal_version_engine, concurrent_change
):
    owner_id, goal_id = _create_committed_goal(goal_version_engine)

    class EditingLLM:
        async def generate(self, _request):
            with Session(goal_version_engine) as writer:
                if concurrent_change == "goal":
                    GoalService(writer).update_goal(
                        goal_id, {"title": "Changed during generation"}, changed_by_user_id=owner_id
                    )
                elif concurrent_change == "criterion":
                    GoalCriteriaService(writer).create_manual(
                        goal_id,
                        owner_id,
                        GoalCriterionCreateRequest(
                            definition=GoalCriterionDefinition(
                                criterion_type=GoalCriterionType.BINARY,
                                description="Existing concurrent criterion",
                                completion_conditions="The outcome is verified.",
                            )
                        ),
                    )
                else:
                    GoalService(writer).transition_status(
                        goal_id, GoalStatus.ARCHIVED, reason="Priorities changed",
                        changed_by_user_id=owner_id,
                    )
            return LLMResponse(
                content=json.dumps({
                    "criteria": [{
                        "criterion_type": "BINARY",
                        "description": "Deploy the release",
                        "completion_conditions": "The release is available.",
                    }]
                }),
                model="test-model",
                provider="test-provider",
            )

    with Session(goal_version_engine) as session:
        goal = GoalRepository(session).get_by_id(goal_id)
        service = GoalCriteriaService(session, EditingLLM())
        with pytest.raises(GoalCriteriaGenerationConflict, match="goal changed"):
            asyncio.run(service.generate(goal, owner_id))

    with Session(goal_version_engine) as verification:
        criteria = GoalCriteriaService(verification).list_for_goal(goal_id)
        repository = GoalRepository(verification)
        goal = repository.get_by_id(goal_id)
        assert len(criteria) == (1 if concurrent_change == "criterion" else 0)
        assert goal.title == (
            "Changed during generation" if concurrent_change == "goal" else "Original goal"
        )
        assert goal.status == (
            GoalStatus.ARCHIVED if concurrent_change == "status" else GoalStatus.DRAFT
        )
        assert repository.get_latest_version(goal_id).version == (
            1 if concurrent_change == "status" else 2
        )


@pytest.mark.integration
def test_proposal_and_operative_selection_on_postgresql(goal_version_engine):
    owner_id = f"phase1-owner-{uuid4().hex}"
    goal_id = f"phase1-goal-{uuid4().hex}"
    now = datetime.now(UTC)
    with Session(goal_version_engine) as session:
        session.add(UserDB(
            id=owner_id,
            name="Owner",
            email=f"{owner_id}@example.test",
            created_at=now,
            updated_at=now,
        ))
        session.flush()
        repository = GoalRepository(session)
        goal = repository.create(goal_id=goal_id, user_id=owner_id, title="Current goal")
        current = repository.get_latest_version(goal_id)
        assert current.definition_kind == "STANDARD"
        assert repository.get_operative_version(goal_id) is None

        goal.operative_goal_version_id = current.id
        session.add(app.db.models.GoalVersionDB(
            id=f"phase1-proposal-{uuid4().hex}",
            goal_id=goal_id,
            version=2,
            origin="USER",
            definition_kind="PROPOSAL",
            content={"title": "Proposed goal"},
            created_by_user_id=owner_id,
            created_at=now,
        ))
        session.flush()
        assert repository.get_latest_version(goal_id).id == current.id
        assert repository.get_operative_version(goal_id).id == current.id
        assert goal.title == "Current goal"
        next_version = repository.add_version(goal, owner_id)
        assert next_version.version == 3
        assert repository.get_latest_version(goal_id).id == next_version.id
        assert repository.get_operative_version(goal_id).id == current.id
        session.rollback()


@pytest.mark.integration
def test_version_snapshot_refreshes_previously_loaded_goal(goal_version_engine):
    owner_id = f"phase1-owner-{uuid4().hex}"
    goal_id = f"phase1-goal-{uuid4().hex}"
    now = datetime.now(UTC)
    with Session(goal_version_engine) as setup:
        setup.add(UserDB(
            id=owner_id,
            name="Owner",
            email=f"{owner_id}@example.test",
            created_at=now,
            updated_at=now,
        ))
        setup.flush()
        GoalRepository(setup).create(goal_id=goal_id, user_id=owner_id, title="Original title")
        setup.commit()

    with Session(goal_version_engine) as stale, Session(goal_version_engine) as writer:
        stale_repository = GoalRepository(stale)
        stale_goal = stale_repository.get_by_id(goal_id)
        assert stale_goal.title == "Original title"
        GoalRepository(writer).update(goal_id, {"title": "Updated title"}, owner_id)
        writer.commit()

        version = stale_repository.add_version(stale_goal, owner_id)
        assert version.version == 3
        assert version.content["title"] == "Updated title"
        stale.rollback()


@pytest.mark.integration
@pytest.mark.parametrize("supersede_during_validation", [False, True])
def test_proposal_validation_stays_bound_to_exact_postgresql_version(
    goal_version_engine, supersede_during_validation
):
    owner_id = f"phase1-owner-{uuid4().hex}"
    goal_id = f"phase1-goal-{uuid4().hex}"
    proposal_id = f"phase1-proposal-{uuid4().hex}"
    now = datetime.now(UTC)
    with Session(goal_version_engine) as setup:
        setup.add(UserDB(
            id=owner_id,
            name="Owner",
            email=f"{owner_id}@example.test",
            created_at=now,
            updated_at=now,
        ))
        setup.flush()
        repository = GoalRepository(setup)
        goal = repository.create(
            goal_id=goal_id,
            user_id=owner_id,
            title="Deliver onboarding refresh",
            description="Release the updated onboarding flow",
            structured_fields={
                "goal_type": "delivery",
                "accountability": "Product engineering lead",
                "deliverables": ["Updated onboarding flow"],
                "success_criteria": [{
                    "criterion_type": "BINARY",
                    "description": "The onboarding refresh is released",
                    "completion_conditions": "The updated flow is available to all new users.",
                }],
            },
        )
        current = repository.get_latest_version(goal_id)
        proposal_content = {**current.content, "title": "Revised onboarding refresh"}
        setup.add(app.db.models.GoalVersionDB(
            id=proposal_id,
            goal_id=goal_id,
            version=2,
            origin="USER",
            definition_kind="PROPOSAL",
            content=proposal_content,
            created_by_user_id=owner_id,
            created_at=now,
        ))
        setup.commit()

    class ProposalLLM:
        async def generate(self, _request):
            if supersede_during_validation:
                with Session(goal_version_engine) as writer:
                    writer.add(app.db.models.GoalVersionDB(
                        id=f"phase1-proposal-{uuid4().hex}",
                        goal_id=goal_id,
                        version=3,
                        origin="USER",
                        definition_kind="PROPOSAL",
                        content={**proposal_content, "title": "Newer proposal"},
                        created_by_user_id=owner_id,
                        created_at=datetime.now(UTC),
                    ))
                    writer.commit()
            return LLMResponse(
                content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
            )

    with Session(goal_version_engine) as session:
        service = GoalValidationRunService(session, ProposalLLM())
        if supersede_during_validation:
            with pytest.raises(ValueError, match="proposal changed during validation"):
                asyncio.run(service.validate_proposal(goal_id, proposal_id, owner_id))
        else:
            run = asyncio.run(service.validate_proposal(goal_id, proposal_id, owner_id))
            assert run.status == "READY"
            assert run.goal_version_id == proposal_id

    with Session(goal_version_engine) as verification:
        repository = GoalRepository(verification)
        history = GoalValidationRunService(verification).get_history(goal_id)
        assert len(history) == 1
        assert history[0].goal_version_id == proposal_id
        assert history[0].input_context["title"] == "Revised onboarding refresh"
        assert repository.get_by_id(goal_id).title == "Deliver onboarding refresh"
        assert repository.get_latest_version(goal_id).id != proposal_id
        if supersede_during_validation:
            latest = repository.get_latest_proposal_version(goal_id)
            assert latest.id != proposal_id
            assert not repository.has_ready_validation_for_version(goal_id, latest.id)


@pytest.mark.integration
@pytest.mark.parametrize("first_commits", [True, False])
def test_concurrent_version_allocation_waits_for_commit_or_rollback(
    goal_version_engine, first_commits
):
    owner_id = f"phase1-owner-{uuid4().hex}"
    goal_id = f"phase1-goal-{uuid4().hex}"
    now = datetime.now(UTC)
    with Session(goal_version_engine) as setup:
        setup.add(UserDB(
            id=owner_id,
            name="Owner",
            email=f"{owner_id}@example.test",
            created_at=now,
            updated_at=now,
        ))
        setup.flush()
        GoalRepository(setup).create(goal_id=goal_id, user_id=owner_id, title="Current goal")
        setup.commit()

    first_allocated = Event()
    release_first = Event()
    second_lock_attempted = Event()

    def allocate_first():
        with Session(goal_version_engine) as session:
            repository = GoalRepository(session)
            version = repository.add_version(repository.get_by_id(goal_id), owner_id)
            first_number = version.version
            first_allocated.set()
            if not release_first.wait(10):
                raise TimeoutError("Timed out waiting to release the first version allocation")
            if first_commits:
                session.commit()
            else:
                session.rollback()
            return first_number

    def allocate_second():
        with Session(goal_version_engine) as session:
            @event.listens_for(session.connection(), "before_cursor_execute")
            def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                if "FOR UPDATE" in statement.upper():
                    second_lock_attempted.set()

            repository = GoalRepository(session)
            version = repository.add_version(repository.get_by_id(goal_id), owner_id)
            second_number = version.version
            session.commit()
            return second_number

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(allocate_first)
        try:
            assert first_allocated.wait(10)
            second = executor.submit(allocate_second)
            assert second_lock_attempted.wait(10)
            assert not second.done()
        finally:
            release_first.set()
        assert first.result(timeout=10) == 2
        assert second.result(timeout=10) == (3 if first_commits else 2)

    with Session(goal_version_engine) as session:
        versions = (
            session.query(app.db.models.GoalVersionDB)
            .filter_by(goal_id=goal_id)
            .order_by(app.db.models.GoalVersionDB.version)
            .all()
        )
        assert [version.version for version in versions] == ([1, 2, 3] if first_commits else [1, 2])
