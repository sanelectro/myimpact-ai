import asyncio
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Event
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import app.db.models
from app.auth import AuthenticatedUser, get_current_user
from app.db.models.team import TeamDB as _TeamDB
from app.db.models.user import UserDB
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models.goal import DEFAULT_SUB_STATUS_BY_GOAL_STATUS, GoalStatus, GoalSubStatus
from app.models.goal_criteria import (
    GoalCriterionCreateRequest,
    GoalCriterionDefinition,
    GoalCriterionType,
    GoalCriterionUpdateRequest,
)
from app.models.llm import LLMResponse
from app.models.milestone import MilestoneCreate, MilestoneStatus
from app.repositories.goal import GoalRepository
from app.services.goal import GoalService
from app.services.goal_baseline_observations import (
    GoalBaselineConflict,
    GoalBaselineObservationService,
)
from app.services.goal_criteria import (
    GoalCriteriaGenerationConflict,
    GoalCriteriaService,
)
from app.services.goal_definition_proposals import (
    GoalDefinitionProposalService,
    GoalProposalChanges,
    GoalProposalConflict,
)
from app.services.goal_hierarchy import GoalHierarchyNotFound, GoalHierarchyService
from app.services.goal_proposal_previews import GoalProposalPreviewService
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


def _create_unselected_ongoing_goal(engine):
    owner_id, goal_id = _create_committed_goal(engine)
    with Session(engine) as session:
        goal = GoalRepository(session).get_by_id(goal_id)
        goal.status = GoalStatus.ACTIVE
        goal.sub_status = GoalSubStatus.ON_TRACK
        base_id = GoalRepository(session).get_latest_version(goal_id).id
        session.commit()
    return owner_id, goal_id, base_id


def _observe_baseline(session, owner_id, goal_id, base_id):
    return GoalBaselineObservationService(session).stage_matching_baseline(
        goal_id=goal_id,
        actor_user_id=owner_id,
        expected_version_id=base_id,
        expected_relationship_revision=0,
    )


@pytest.mark.integration
def test_baseline_observation_selects_only_matching_current_snapshot(goal_version_engine):
    owner_id, goal_id, base_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        observation = _observe_baseline(session, owner_id, goal_id, base_id)
        assert observation.historical_effectivity == "UNKNOWN"
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id == base_id
        session.rollback()

    with Session(goal_version_engine) as session:
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id is None
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        observation = _observe_baseline(session, owner_id, goal_id, base_id)
        session.commit()
        observed_at = observation.observed_at
        retry = _observe_baseline(session, owner_id, goal_id, base_id)
        assert retry.observed_at == observed_at
        assert retry.historical_effectivity == "UNKNOWN"
        assert GoalRepository(session).get_by_id(goal_id).title == "Original goal"
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalVersionApprovalDB)
            .where(app.db.models.GoalVersionApprovalDB.goal_id == goal_id)
        ) == 0
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(
                    text("UPDATE goal_baseline_observations SET historical_effectivity='UNKNOWN' WHERE goal_id=:goal"),
                    {"goal": goal_id},
                )
        session.rollback()
        assert GoalRepository(session).delete(goal_id)
        session.commit()
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None


@pytest.mark.integration
def test_baseline_observation_rejects_mismatch_and_unauthorized_owner(goal_version_engine):
    owner_id, goal_id, base_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        with pytest.raises(ValueError, match="Goal not found"):
            _observe_baseline(session, "another-user", goal_id, base_id)
        session.rollback()
        with pytest.raises(GoalBaselineConflict, match="version changed"):
            _observe_baseline(session, owner_id, goal_id, "stale-version")
        session.rollback()
        MilestoneService(session).create_milestone(goal_id, MilestoneCreate(title="New milestone"))
        with pytest.raises(GoalBaselineConflict, match="does not match"):
            _observe_baseline(session, owner_id, goal_id, base_id)
        session.rollback()
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id is None


@pytest.mark.integration
def test_baseline_observation_rejects_incomplete_legacy_snapshot(goal_version_engine):
    owner_id, goal_id, _ = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        legacy = app.db.models.GoalVersionDB(
            id=f"phase1-incomplete-{uuid4().hex}",
            goal_id=goal_id,
            version=2,
            origin="LEGACY",
            definition_kind="STANDARD",
            content={"title": "Original goal"},
            created_at=datetime.now(UTC),
        )
        session.add(legacy)
        session.commit()
        with pytest.raises(GoalBaselineConflict, match="does not match"):
            _observe_baseline(session, owner_id, goal_id, legacy.id)
        session.rollback()
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id is None


@pytest.mark.integration
def test_observed_baseline_preserves_legacy_reads_and_uses_approved_criterion(goal_version_engine):
    owner_id, goal_id, _ = _create_unselected_ongoing_goal(goal_version_engine)
    original = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Deploy the release",
        completion_conditions="The release is available.",
    )
    pending = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Pending revision",
        completion_conditions="The new release is available.",
    )
    with Session(goal_version_engine) as session:
        criteria = GoalCriteriaService(session)
        criterion = criteria.create_manual(
            goal_id, owner_id, GoalCriterionCreateRequest(definition=original)
        )
        approved_id = criterion.versions[0].id
        criteria.approve_version(goal_id, criterion.id, approved_id, owner_id)
        criteria.add_version(
            goal_id, criterion.id, owner_id, GoalCriterionUpdateRequest(definition=pending)
        )
        MilestoneService(session).create_milestone(goal_id, MilestoneCreate(title="New milestone"))
        repository = GoalRepository(session)
        source_id = repository.get_latest_version(goal_id).id
        before_eligibility = GoalService(session).get_evidence_submission_eligibility(
            repository.get_by_id(goal_id)
        )

        service = GoalBaselineObservationService(session)
        observation = service.stage_observed_baseline(
            goal_id=goal_id,
            actor_user_id=owner_id,
            expected_source_version_id=source_id,
            expected_relationship_revision=0,
        )
        observed_id = observation.goal_version_id
        session.commit()
        observed = session.get(app.db.models.GoalVersionDB, observed_id)
        assert observed.definition_kind == "OBSERVED"
        assert observed.content["criterion_versions"][0]["version_id"] == approved_id
        assert observed.content["criterion_versions"][0]["definition"]["description"] == original.description
        assert observed.content["milestone_definitions"][0]["title"] == "New milestone"
        assert observation.historical_effectivity == "UNKNOWN"
        assert observation.source_standard_version_id == source_id
        assert repository.get_latest_version(goal_id).id == source_id
        assert GoalService(session).get_evidence_submission_eligibility(
            repository.get_by_id(goal_id)
        ) == before_eligibility
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalVersionApprovalDB)
            .where(app.db.models.GoalVersionApprovalDB.goal_id == goal_id)
        ) == 0
        retry = service.stage_observed_baseline(
            goal_id=goal_id,
            actor_user_id=owner_id,
            expected_source_version_id=source_id,
            expected_relationship_revision=0,
        )
        assert retry.goal_version_id == observed_id
        session.commit()

        proposal = _stage_text(session, owner_id, goal_id, observed_id, key="observed-proposal")
        session.commit()
        assert proposal.outcome == "CREATED"
        assert session.get(app.db.models.GoalVersionDB, proposal.version_id).content[
            "criterion_versions"
        ][0]["version_id"] == approved_id
        assert repository.get_latest_version(goal_id).id == source_id

        GoalService(session).update_goal(
            goal_id, {"title": "Changed after observation"}, changed_by_user_id=owner_id
        )
        with pytest.raises(GoalProposalConflict, match="baseline.*changed"):
            _stage_text(
                session, owner_id, goal_id, observed_id,
                key="stale-observation", revision=1,
            )
        session.rollback()


@pytest.mark.integration
def test_observed_baseline_rolls_back_without_fabricating_history(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        service = GoalBaselineObservationService(session)
        with pytest.raises(ValueError, match="Goal not found"):
            service.stage_observed_baseline(
                goal_id=goal_id, actor_user_id="other", expected_source_version_id=source_id,
                expected_relationship_revision=0,
            )
        session.rollback()
        with pytest.raises(GoalBaselineConflict, match="version changed"):
            service.stage_observed_baseline(
                goal_id=goal_id, actor_user_id=owner_id, expected_source_version_id="stale",
                expected_relationship_revision=0,
            )
        session.rollback()
        observation = service.stage_observed_baseline(
            goal_id=goal_id, actor_user_id=owner_id, expected_source_version_id=source_id,
            expected_relationship_revision=0,
        )
        observed_id = observation.goal_version_id
        session.rollback()

    with Session(goal_version_engine) as session:
        assert session.get(app.db.models.GoalVersionDB, observed_id) is None
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id is None
        assert GoalRepository(session).get_latest_version(goal_id).id == source_id


@pytest.mark.integration
def test_observed_baseline_rejects_unapproved_current_criterion(goal_version_engine):
    owner_id, goal_id, _ = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        criterion = GoalCriteriaService(session).create_manual(
            goal_id,
            owner_id,
            GoalCriterionCreateRequest(
                definition=GoalCriterionDefinition(
                    criterion_type=GoalCriterionType.BINARY,
                    description="Deploy the release",
                    completion_conditions="The release is available.",
                )
            ),
        )
        criterion.current_version = 1
        session.commit()
        source_id = GoalRepository(session).get_latest_version(goal_id).id
        with pytest.raises(ValueError, match="missing or not approved"):
            GoalBaselineObservationService(session).stage_observed_baseline(
                goal_id=goal_id, actor_user_id=owner_id,
                expected_source_version_id=source_id, expected_relationship_revision=0,
            )
        session.rollback()
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id is None


@pytest.mark.integration
def test_concurrent_observed_baseline_reuses_original_observation(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    attempted = Event()
    arguments = {
        "goal_id": goal_id,
        "actor_user_id": owner_id,
        "expected_source_version_id": source_id,
        "expected_relationship_revision": 0,
    }
    with Session(goal_version_engine) as first:
        observation = GoalBaselineObservationService(first).stage_observed_baseline(**arguments)
        observed_id = observation.goal_version_id

        def retry():
            with Session(goal_version_engine) as second:
                @event.listens_for(second.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        attempted.set()

                result = GoalBaselineObservationService(second).stage_observed_baseline(**arguments)
                return result.goal_version_id

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(retry)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                first.commit()
                assert pending.result(timeout=10) == observed_id
            finally:
                first.rollback()
    with Session(goal_version_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalVersionDB).where(
                app.db.models.GoalVersionDB.goal_id == goal_id,
                app.db.models.GoalVersionDB.definition_kind == "OBSERVED",
            )
        ) == 1
        assert GoalRepository(session).get_latest_version(goal_id).id == source_id


@pytest.mark.integration
def test_observed_baseline_validation_rechecks_source_after_provider(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        observation = GoalBaselineObservationService(session).stage_observed_baseline(
            goal_id=goal_id, actor_user_id=owner_id,
            expected_source_version_id=source_id, expected_relationship_revision=0,
        )
        observed_id = observation.goal_version_id
        session.commit()
        proposal = _stage_text(session, owner_id, goal_id, observed_id, key="validate-observed")
        session.commit()

    class ChangingLLM:
        async def generate(self, _request):
            with Session(goal_version_engine) as writer:
                GoalService(writer).update_goal(
                    goal_id, {"title": "Changed during validation"}, changed_by_user_id=owner_id
                )
            return LLMResponse(
                content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
            )

    with Session(goal_version_engine) as session:
        validator = GoalValidationRunService(session, ChangingLLM())
        with pytest.raises(GoalProposalConflict, match="changed during validation"):
            asyncio.run(
                validator.validate_prepared_proposal(goal_id, proposal.version_id, owner_id)
            )
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalValidationRunDB).where(
                app.db.models.GoalValidationRunDB.goal_version_id == proposal.version_id
            )
        ) == 1


@pytest.mark.integration
def test_observed_baseline_requires_same_goal_standard_source(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    _, _, other_source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        version = GoalRepository(session).add_observed_baseline_version(
            GoalRepository(session).get_by_id_for_update(goal_id), owner_id
        )
        session.flush()
        for source in (None, other_source_id, version.id):
            with pytest.raises(DBAPIError):
                with session.begin_nested():
                    session.execute(
                        text("""
                            INSERT INTO goal_baseline_observations
                                (goal_id, goal_version_id, source_standard_version_id,
                                 observed_by_user_id, observed_at)
                            VALUES (:goal, :version, :source, :owner, now())
                        """),
                        {"goal": goal_id, "version": version.id, "source": source, "owner": owner_id},
                    )
        session.rollback()
        assert GoalRepository(session).get_latest_version(goal_id).id == source_id


@pytest.mark.integration
def test_baseline_observation_preserves_existing_user_cascade(goal_version_engine):
    owner_id, goal_id, base_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        _observe_baseline(session, owner_id, goal_id, base_id)
        session.commit()
        session.execute(text("DELETE FROM users WHERE id = :owner"), {"owner": owner_id})
        session.commit()
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        assert GoalRepository(session).get_by_id(goal_id) is None


@pytest.mark.integration
def test_concurrent_baseline_observations_reuse_one_record(goal_version_engine):
    owner_id, goal_id, base_id = _create_unselected_ongoing_goal(goal_version_engine)
    attempted = Event()
    with Session(goal_version_engine) as first:
        original = _observe_baseline(first, owner_id, goal_id, base_id)

        def observe():
            with Session(goal_version_engine) as second:
                @event.listens_for(second.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        attempted.set()

                result = _observe_baseline(second, owner_id, goal_id, base_id)
                return result.goal_version_id, result.observed_at

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(observe)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                first.commit()
                assert pending.result(timeout=10) == (base_id, original.observed_at)
            finally:
                first.rollback()
    with Session(goal_version_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalBaselineObservationDB)
            .where(app.db.models.GoalBaselineObservationDB.goal_id == goal_id)
        ) == 1


def _stage_text(session, owner_id, goal_id, base_id, *, key, revision=0, title="Revised goal"):
    return GoalDefinitionProposalService(session).stage_proposal(
        goal_id=goal_id,
        actor_user_id=owner_id,
        idempotency_key=key,
        expected_base_version_id=base_id,
        expected_proposal_revision=revision,
        expected_relationship_revision=0,
        changes=GoalProposalChanges(title=title),
    )


def _stage_observed_text(
    session, owner_id, goal_id, source_id, *, key, revision=0, title="Revised goal"
):
    return GoalDefinitionProposalService(session).stage_observed_proposal(
        goal_id=goal_id,
        actor_user_id=owner_id,
        idempotency_key=key,
        expected_source_version_id=source_id,
        expected_proposal_revision=revision,
        expected_relationship_revision=0,
        changes=GoalProposalChanges(title=title),
    )


@pytest.mark.integration
def test_observation_and_proposal_commit_and_retry_as_one_command(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        result = _stage_observed_text(session, owner_id, goal_id, source_id, key="combined")
        observed_id = session.get(app.db.models.GoalBaselineObservationDB, goal_id).goal_version_id
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id).base_version_id == observed_id
        assert GoalRepository(session).get_by_id(goal_id).title == "Original goal"
        session.commit()

        GoalService(session).update_goal(
            goal_id, {"title": "Changed after preparation"}, changed_by_user_id=owner_id
        )
        retry = _stage_observed_text(session, owner_id, goal_id, source_id, key="combined")
        assert retry == result
        with pytest.raises(GoalProposalConflict, match="different request"):
            _stage_observed_text(
                session, owner_id, goal_id, source_id, key="combined", title="Different request"
            )
        with pytest.raises(GoalProposalConflict, match="different request"):
            _stage_observed_text(session, owner_id, goal_id, "other-source", key="combined")
        session.rollback()

    with Session(goal_version_engine) as session:
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id).goal_version_id == observed_id
        assert session.get(app.db.models.GoalVersionDB, result.version_id).content["title"] == "Revised goal"
        assert GoalRepository(session).get_by_id(goal_id).title == "Changed after preparation"


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["invalid_dates", "receipt_write"])
def test_combined_preparation_failure_leaves_no_partial_changes(goal_version_engine, failure):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        service = GoalDefinitionProposalService(session)
        connection = session.connection()

        def fail_receipt(_conn, _cursor, statement, _parameters, _context, _executemany):
            if "INSERT INTO goal_command_receipts" in statement:
                raise RuntimeError("Injected receipt failure")

        if failure == "receipt_write":
            event.listen(connection, "before_cursor_execute", fail_receipt)
        try:
            changes = (
                GoalProposalChanges(start_date=date(2027, 1, 1), end_date=date(2026, 12, 31))
                if failure == "invalid_dates"
                else GoalProposalChanges(title="Revised goal")
            )
            expected_error = ValueError if failure == "invalid_dates" else RuntimeError
            with pytest.raises(expected_error):
                service.stage_observed_proposal(
                    goal_id=goal_id,
                    actor_user_id=owner_id,
                    idempotency_key="failing",
                    expected_source_version_id=source_id,
                    expected_proposal_revision=0,
                    expected_relationship_revision=0,
                    changes=changes,
                )
        finally:
            if failure == "receipt_write":
                event.remove(connection, "before_cursor_execute", fail_receipt)
        session.commit()

    with Session(goal_version_engine) as session:
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id is None
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "failing")
        ) is None
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalVersionDB).where(
                app.db.models.GoalVersionDB.goal_id == goal_id,
                app.db.models.GoalVersionDB.definition_kind != "STANDARD",
            )
        ) == 0


@pytest.mark.integration
def test_combined_preparation_rollback_removes_all_staged_changes(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        result = _stage_observed_text(session, owner_id, goal_id, source_id, key="rollback-both")
        observed_id = session.get(app.db.models.GoalBaselineObservationDB, goal_id).goal_version_id
        session.rollback()
    with Session(goal_version_engine) as session:
        assert GoalRepository(session).get_by_id(goal_id).operative_goal_version_id is None
        assert session.get(app.db.models.GoalBaselineObservationDB, goal_id) is None
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None
        assert session.get(app.db.models.GoalVersionDB, observed_id) is None
        assert session.get(app.db.models.GoalVersionDB, result.version_id) is None
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "rollback-both")
        ) is None


@pytest.mark.integration
def test_combined_noop_records_observation_but_no_proposal(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        with pytest.raises(ValueError, match="Goal not found"):
            _stage_observed_text(session, "other-user", goal_id, source_id, key="unauthorized")
        session.rollback()
        result = _stage_observed_text(
            session, owner_id, goal_id, source_id, key="noop-combined", title="Original   goal"
        )
        observation = session.get(app.db.models.GoalBaselineObservationDB, goal_id)
        assert result.outcome == "NO_CHANGE"
        assert result.revision == 0
        assert result.version_id == observation.goal_version_id
        session.commit()
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalVersionDB).where(
                app.db.models.GoalVersionDB.goal_id == goal_id,
                app.db.models.GoalVersionDB.definition_kind == "PROPOSAL",
            )
        ) == 0
        assert GoalRepository(session).get_latest_version(goal_id).id == source_id


@pytest.mark.integration
def test_concurrent_combined_retry_returns_one_receipt(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    attempted = Event()
    with Session(goal_version_engine) as first:
        result = _stage_observed_text(first, owner_id, goal_id, source_id, key="same-combined")

        def retry():
            with Session(goal_version_engine) as second:
                @event.listens_for(second.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "pg_advisory_xact_lock" in statement:
                        attempted.set()

                retried = _stage_observed_text(second, owner_id, goal_id, source_id, key="same-combined")
                second.commit()
                return retried

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(retry)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                first.commit()
                assert pending.result(timeout=10) == result
            finally:
                first.rollback()
    with Session(goal_version_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalVersionDB).where(
                app.db.models.GoalVersionDB.goal_id == goal_id,
                app.db.models.GoalVersionDB.definition_kind == "OBSERVED",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalCommandReceiptDB)
            .where(app.db.models.GoalCommandReceiptDB.goal_id == goal_id)
        ) == 1


@pytest.mark.integration
def test_concurrent_combined_requests_recheck_proposal_revision(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    attempted = Event()
    with Session(goal_version_engine) as first:
        result = _stage_observed_text(first, owner_id, goal_id, source_id, key="first-combined")

        def competing():
            with Session(goal_version_engine) as second:
                @event.listens_for(second.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        attempted.set()

                with pytest.raises(GoalProposalConflict, match="proposal changed"):
                    _stage_observed_text(
                        second, owner_id, goal_id, source_id,
                        key="second-combined", title="Competing proposal",
                    )

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
        assert head.proposal_version_id == result.version_id
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "second-combined")
        ) is None


@pytest.mark.integration
def test_combined_command_cannot_reuse_key_from_direct_preparation(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        observation = GoalBaselineObservationService(session).stage_observed_baseline(
            goal_id=goal_id, actor_user_id=owner_id,
            expected_source_version_id=source_id, expected_relationship_revision=0,
        )
        observed_id = observation.goal_version_id
        session.commit()
        _stage_text(session, owner_id, goal_id, observed_id, key="direct")
        session.commit()
        with pytest.raises(GoalProposalConflict, match="different request"):
            _stage_observed_text(session, owner_id, goal_id, source_id, key="direct")
        session.rollback()


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
def test_milestone_proposals_are_isolated_and_require_supported_validation(goal_version_engine):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    with Session(goal_version_engine) as session:
        milestone = MilestoneService(session).create_milestone(
            goal_id, MilestoneCreate(
                title="Original milestone", description="Original description",
                status=MilestoneStatus.COMPLETED, due_date=date(2026, 12, 1),
            )
        )
        milestone_id = milestone.id
        observation = GoalBaselineObservationService(session).stage_observed_baseline(
            goal_id=goal_id, actor_user_id=owner_id,
            expected_source_version_id=source_id, expected_relationship_revision=0,
        )
        base_id = observation.goal_version_id
        session.commit()
        service = GoalDefinitionProposalService(session)
        arguments = {
            "goal_id": goal_id, "actor_user_id": owner_id,
            "expected_base_version_id": base_id, "expected_relationship_revision": 0,
        }
        with pytest.raises(ValueError, match="Milestone not found"):
            service.stage_proposal(
                **arguments, idempotency_key="missing-milestone",
                expected_proposal_revision=0,
                changes=GoalProposalChanges(milestone_updates=[
                    {"milestone_id": milestone_id, "title": "Changed"},
                    {"milestone_id": "other-goal-milestone", "title": "Invalid"},
                ]),
            )
        session.rollback()
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None
        assert session.get(
            app.db.models.GoalCommandReceiptDB,
            (owner_id, "PREPARE_DEFINITION", "missing-milestone"),
        ) is None

        noop = service.stage_proposal(
            **arguments, idempotency_key="milestone-noop", expected_proposal_revision=0,
            changes=GoalProposalChanges(milestone_updates=[
                {"milestone_id": milestone_id, "title": "Original  milestone"},
            ]),
        )
        assert (noop.outcome, noop.revision, noop.version_id) == ("NO_CHANGE", 0, base_id)
        session.commit()
        proposal = service.stage_proposal(
            **arguments, idempotency_key="milestone-change", expected_proposal_revision=0,
            changes=GoalProposalChanges(milestone_updates=[{
                "milestone_id": milestone_id, "title": "Revised milestone",
                "description": None, "due_date": "2027-01-15",
            }]),
        )
        session.commit()
        candidate = session.get(app.db.models.GoalVersionDB, proposal.version_id)
        assert candidate.content["milestone_definitions"] == [{
            "milestone_id": milestone_id, "title": "Revised milestone",
            "description": None, "completion_criteria": None, "source": "manual",
            "due_date": "2027-01-15",
        }]
        current = session.get(app.db.models.MilestoneDB, milestone_id)
        assert (current.title, current.description, current.due_date, current.status) == (
            "Original milestone", "Original description", date(2026, 12, 1),
            MilestoneStatus.COMPLETED,
        )
        assert GoalRepository(session).get_latest_version(goal_id).id == source_id
        assert session.get(app.db.models.GoalVersionDB, base_id).content["milestone_definitions"][0][
            "title"
        ] == "Original milestone"
        assert service.stage_proposal(
            **arguments, idempotency_key="milestone-change", expected_proposal_revision=0,
            changes=GoalProposalChanges(milestone_updates=[{
                "milestone_id": milestone_id, "title": "Revised milestone",
                "description": None, "due_date": "2027-01-15",
            }]),
        ) == proposal

        class UnexpectedLLM:
            async def generate(self, _request):
                raise AssertionError("Unsupported milestone changes must not reach validation")

        validator = GoalValidationRunService(session, UnexpectedLLM())
        for validate in (
            validator.validate_prepared_proposal,
            validator.validate_proposal,
            validator.stage_prepared_proposal_validation,
        ):
            with pytest.raises(GoalProposalConflict, match="milestone definitions is not supported"):
                asyncio.run(validate(goal_id, proposal.version_id, owner_id))
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalValidationRunDB).where(
                app.db.models.GoalValidationRunDB.goal_version_id == proposal.version_id
            )
        ) == 0

        reverted = service.stage_proposal(
            **arguments, idempotency_key="milestone-revert", expected_proposal_revision=1,
            changes=GoalProposalChanges(milestone_updates=[{
                "milestone_id": milestone_id, "title": "Original milestone",
                "description": "Original description", "due_date": "2026-12-01",
            }]),
        )
        session.commit()
        class NormalLLM:
            async def generate(self, _request):
                return LLMResponse(
                    content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
                )

        run = asyncio.run(
            GoalValidationRunService(session, NormalLLM()).validate_prepared_proposal(
                goal_id, reverted.version_id, owner_id
            )
        )
        assert run.goal_version_id == reverted.version_id
        assert session.get(app.db.models.MilestoneDB, milestone_id).status == MilestoneStatus.COMPLETED


@pytest.mark.integration
def test_authenticated_proposal_api_prepares_previews_and_validates(
    goal_version_engine, monkeypatch
):
    owner_id, goal_id, source_id = _create_unselected_ongoing_goal(goal_version_engine)
    identity = {"user": owner_id}

    def override_db():
        with Session(goal_version_engine) as db:
            yield db

    class NormalLLM:
        async def generate(self, _request):
            return LLMResponse(
                content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
            )

    overrides = fastapi_app.dependency_overrides.copy()
    fastapi_app.dependency_overrides[get_db] = override_db
    fastapi_app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        identity["user"], "owner@example.test", None, {"myimpact-ai"}
    )
    monkeypatch.setattr("app.services.goal_validation.create_llm_service", lambda: NormalLLM())
    try:
        with TestClient(fastapi_app) as client:
            path = f"/api/v1/goals/{goal_id}/definition-proposal"
            state = client.get(path)
            assert state.status_code == 200, state.text
            assert state.json()["latest_standard_version_id"] == source_id
            assert state.json()["proposal"] is None
            request = {
                "idempotency_key": "api-first",
                "expected_source_version_id": source_id,
                "expected_proposal_revision": 0,
                "expected_relationship_revision": 0,
                "changes": {"title": "Revised goal"},
            }
            response = client.post(path, json=request)
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["outcome"] == "CREATED"
            assert client.post(path, json=request).json() == result
            conflict = client.post(path, json={**request, "changes": {"title": "Different"}})
            assert conflict.status_code == 409, conflict.text
            state = client.get(path).json()
            assert state["proposal"]["content"]["title"] == "Revised goal"
            version = {"proposal_version_id": result["version_id"]}
            preview = client.post(f"{path}/date-preview", json=version)
            assert preview.status_code == 200, preview.text
            assert preview.json()["conflicts"] == []
            validation = client.post(f"{path}/validate", json=version)
            assert validation.status_code == 200, validation.text
            assert validation.json()["goal_version_id"] == result["version_id"]
            assert client.get(path).json()["proposal"]["latest_validation_id"] == validation.json()["id"]
            with Session(goal_version_engine) as reader:
                assert GoalRepository(reader).get_by_id(goal_id).title == "Original goal"
            with Session(goal_version_engine) as writer:
                GoalService(writer).update_goal(
                    goal_id, {"title": "Changed separately"}, changed_by_user_id=owner_id
                )
            assert client.get(path).status_code == 409
            assert client.post(f"{path}/date-preview", json=version).status_code == 409
            identity["user"] = "other-user"
            assert client.get(path).status_code == 404
            assert client.post(path, json=request).status_code == 404
            assert client.post(f"{path}/validate", json=version).status_code == 404
            assert client.post(f"{path}/date-preview", json=version).status_code == 404
        with Session(goal_version_engine) as reader:
            assert GoalRepository(reader).get_by_id(goal_id).title == "Changed separately"
    finally:
        fastapi_app.dependency_overrides.clear()
        fastapi_app.dependency_overrides.update(overrides)


@pytest.mark.integration
def test_prepared_proposal_date_preview_rechecks_exact_head(goal_version_engine, monkeypatch):
    owner_id, goal_id, _ = _create_selected_baseline(goal_version_engine)
    child_id = str(uuid4())
    with Session(goal_version_engine) as session:
        repository = GoalRepository(session)
        goal = repository.update(
            goal_id, {"start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)}, owner_id
        )
        base_id = repository.get_latest_version(goal_id).id
        goal.operative_goal_version_id = base_id
        child = repository.create(goal_id=child_id, user_id=owner_id, title="Child")
        child.start_date, child.end_date = date(2026, 3, 1), date(2026, 6, 1)
        session.commit()
        GoalHierarchyService(session).set_parent(child_id, owner_id, goal_id, 0, None)

        arguments = {
            "goal_id": goal_id, "actor_user_id": owner_id, "expected_base_version_id": base_id,
            "expected_relationship_revision": 0,
        }
        proposal = GoalDefinitionProposalService(session).stage_proposal(
            **arguments, idempotency_key="preview", expected_proposal_revision=0,
            changes=GoalProposalChanges(start_date=date(2026, 4, 1)),
        )
        session.commit()
        previewer = GoalProposalPreviewService(session)
        preview = previewer.preview_dates(goal_id, proposal.version_id, owner_id)
        assert preview.goal_id == goal_id
        assert preview.proposal_version_id == proposal.version_id
        assert [(item.child_goal_id, item.child_field) for item in preview.conflicts] == [
            (child_id, "start_date"),
        ]
        session.rollback()
        with pytest.raises(ValueError, match="Goal proposal not found"):
            previewer.preview_dates(goal_id, proposal.version_id, "other")
        session.rollback()

        original_preview = previewer.hierarchy.preview_proposed_date_conflicts

        def supersede_before_lock(*args):
            with Session(goal_version_engine) as writer:
                GoalDefinitionProposalService(writer).stage_proposal(
                    **arguments, idempotency_key="newer-preview", expected_proposal_revision=1,
                    changes=GoalProposalChanges(start_date=date(2026, 2, 1)),
                )
                writer.commit()
            return original_preview(*args)

        monkeypatch.setattr(
            previewer.hierarchy, "preview_proposed_date_conflicts", supersede_before_lock
        )
        with pytest.raises(GoalProposalConflict, match="superseded"):
            previewer.preview_dates(goal_id, proposal.version_id, owner_id)
        session.rollback()
        assert repository.get_by_id(goal_id).start_date == date(2026, 1, 1)
        assert repository.get_by_id(child_id).start_date == date(2026, 3, 1)


@pytest.mark.integration
def test_hierarchy_date_preview_checks_current_neighbors_without_mutation(goal_version_engine):
    owner_id, goal_id = _create_committed_goal(goal_version_engine)
    parent_id, child_id, completed_id, undated_id = (str(uuid4()) for _ in range(4))
    with Session(goal_version_engine) as session:
        repository = GoalRepository(session)
        for item_id, title, start, end, status in (
            (parent_id, "Parent", date(2026, 1, 1), date(2026, 12, 31), GoalStatus.ACTIVE),
            (child_id, "Child", date(2026, 3, 1), date(2026, 6, 1), GoalStatus.ACTIVE),
            (completed_id, "Completed", date(2025, 1, 1), date(2027, 1, 1), GoalStatus.COMPLETED),
            (undated_id, "Undated", None, None, GoalStatus.DRAFT),
        ):
            item = repository.create(goal_id=item_id, user_id=owner_id, title=title)
            item.start_date, item.end_date, item.status = start, end, status
            item.sub_status = DEFAULT_SUB_STATUS_BY_GOAL_STATUS[status]
        goal = repository.get_by_id(goal_id)
        goal.start_date, goal.end_date, goal.status = date(2026, 2, 1), date(2026, 9, 1), GoalStatus.ACTIVE
        goal.sub_status = GoalSubStatus.ON_TRACK
        session.commit()
        hierarchy = GoalHierarchyService(session)
        hierarchy.set_parent(goal_id, owner_id, parent_id, 0, None)
        for child in (child_id, completed_id, undated_id):
            hierarchy.set_parent(child, owner_id, goal_id, 0, None)

        conflicts = hierarchy.preview_proposed_date_conflicts(
            goal_id, owner_id, date(2026, 4, 1), date(2026, 5, 1)
        )
        assert [(item.child_goal_id, item.child_field, item.parent_field) for item in conflicts] == [
            (child_id, "start_date", "start_date"),
            (child_id, "end_date", "end_date"),
        ]
        session.rollback()
        conflicts = hierarchy.preview_proposed_date_conflicts(
            goal_id, owner_id, date(2025, 12, 1), date(2027, 1, 1)
        )
        assert [(item.child_goal_id, item.child_field, item.parent_field) for item in conflicts] == [
            (goal_id, "start_date", "start_date"),
            (goal_id, "end_date", "end_date"),
        ]
        session.rollback()
        assert hierarchy.preview_proposed_date_conflicts(goal_id, owner_id, None, None) == []
        session.rollback()
        with pytest.raises(ValueError, match="before start"):
            hierarchy.preview_proposed_date_conflicts(
                goal_id, owner_id, date(2027, 1, 1), date(2026, 1, 1)
            )
        with pytest.raises(GoalHierarchyNotFound, match="Goal not found"):
            hierarchy.preview_proposed_date_conflicts(goal_id, "other-user", None, None)
        session.rollback()
        assert repository.get_by_id(goal_id).start_date == date(2026, 2, 1)
        assert repository.get_by_id(child_id).end_date == date(2026, 6, 1)


@pytest.mark.integration
def test_hierarchy_date_preview_serializes_reparenting(goal_version_engine):
    owner_id, goal_id = _create_committed_goal(goal_version_engine)
    child_id = str(uuid4())
    with Session(goal_version_engine) as setup:
        GoalRepository(setup).create(goal_id=child_id, user_id=owner_id, title="Child")
        setup.commit()
        GoalHierarchyService(setup).set_parent(child_id, owner_id, goal_id, 0, None)
    attempted = Event()
    with Session(goal_version_engine) as session:
        GoalHierarchyService(session).preview_proposed_date_conflicts(goal_id, owner_id, None, None)

        def detach():
            with Session(goal_version_engine) as writer:
                @event.listens_for(writer.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "pg_advisory_xact_lock" in statement:
                        attempted.set()

                return GoalHierarchyService(writer).set_parent(child_id, owner_id, None, 1, "Move")

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(detach)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                session.commit()
                assert pending.result(timeout=10).parent_goal_id is None
            finally:
                session.rollback()


@pytest.mark.integration
def test_proposal_readiness_requires_latest_exact_supported_result(goal_version_engine):
    owner_id, goal_id, _ = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        repository = GoalRepository(session)
        goal = repository.update(goal_id, {"structured_fields": {
            "accountability": "Employee owner",
            "success_criteria": [{
                "criterion_type": "BINARY",
                "description": "Deliver the result",
                "completion_conditions": "The result is available",
            }],
        }}, owner_id)
        base_id = repository.get_latest_version(goal_id).id
        goal.operative_goal_version_id = base_id
        session.commit()
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="ready-exact")
        session.commit()

        class NormalLLM:
            async def generate(self, _request):
                return LLMResponse(
                    content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
                )

        validator = GoalValidationRunService(session, NormalLLM())
        repository.get_by_id_for_update(goal_id)
        with pytest.raises(GoalProposalConflict, match="latest proposal validation"):
            validator.require_ready_proposal_validation(goal_id, proposal.version_id, owner_id, "missing")
        session.rollback()
        ready = asyncio.run(
            validator.stage_prepared_proposal_validation(goal_id, proposal.version_id, owner_id)
        )
        assert ready.status == "READY"
        ready_id = ready.id
        session.commit()
        repository.get_by_id_for_update(goal_id)
        assert validator.require_ready_proposal_validation(
            goal_id, proposal.version_id, owner_id, ready_id
        ).id == ready_id
        with pytest.raises(ValueError, match="Goal proposal not found"):
            validator.require_ready_proposal_validation(goal_id, proposal.version_id, "other", ready_id)
        with pytest.raises(GoalProposalConflict, match="latest proposal validation"):
            validator.require_ready_proposal_validation(goal_id, proposal.version_id, owner_id, "other")
        session.rollback()

        for field, value in (
            ("actor_user_id", "other"),
            ("rule_set_version", "outdated-rules"),
            ("prompt_version", "outdated-prompt"),
            ("input_context", {}),
        ):
            source = session.get(app.db.models.GoalValidationRunDB, ready_id)
            values = {
                name: getattr(source, name)
                for name in (
                    "goal_id", "goal_version_id", "status", "findings", "input_context",
                    "result_context", "rule_set_version", "prompt_version",
                    "model_provider", "model_version", "actor_user_id",
                )
            }
            values[field] = value
            run = app.db.models.GoalValidationRunDB(
                id=str(uuid4()), created_at=source.created_at + timedelta(seconds=1), **values
            )
            session.add(run)
            session.flush()
            repository.get_by_id_for_update(goal_id)
            with pytest.raises(GoalProposalConflict, match="validation context changed"):
                validator.require_ready_proposal_validation(goal_id, proposal.version_id, owner_id, run.id)
            session.rollback()

        class AmbiguousLLM:
            async def generate(self, _request):
                return LLMResponse(
                    content=json.dumps({"issues": [{
                        "code": "ambiguous_intent",
                        "evidence": [{"field": "title", "quote": "Revised goal"}],
                    }]}),
                    model="test-model", provider="test-provider",
                )

        latest = asyncio.run(
            GoalValidationRunService(session, AmbiguousLLM()).stage_prepared_proposal_validation(
                goal_id, proposal.version_id, owner_id
            )
        )
        assert latest.status != "READY"
        latest_id = latest.id
        session.commit()
        repository.get_by_id_for_update(goal_id)
        for run_id in (ready_id, latest_id):
            with pytest.raises(GoalProposalConflict, match="latest proposal validation"):
                validator.require_ready_proposal_validation(goal_id, proposal.version_id, owner_id, run_id)
        assert not repository.has_ready_validation_for_version(goal_id, proposal.version_id)


@pytest.mark.integration
def test_proposal_readiness_rechecks_time_sensitive_requirements(goal_version_engine, monkeypatch):
    owner_id, goal_id, _ = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        repository = GoalRepository(session)
        goal = repository.update(goal_id, {"structured_fields": {
            "accountability": "Employee owner",
            "success_criteria": [{
                "criterion_type": "BINARY",
                "description": "Deliver the result",
                "completion_conditions": "The result is available",
            }],
            "deferred_requirements": [{
                "requirement": "baseline",
                "reason": "Await measurement",
                "due_date": (datetime.now(UTC).date() - timedelta(days=1)).isoformat(),
                "state": "OPEN",
            }],
        }}, owner_id)
        base_id = repository.get_latest_version(goal_id).id
        goal.operative_goal_version_id = base_id
        session.commit()
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="ready-dynamic")
        session.commit()

        class NormalLLM:
            async def generate(self, _request):
                return LLMResponse(
                    content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
                )

        class EarlierDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) - timedelta(days=2)

        validator = GoalValidationRunService(session, NormalLLM())
        with monkeypatch.context() as patch:
            patch.setattr("app.services.goal_validation_runs.datetime", EarlierDatetime)
            run = asyncio.run(
                validator.stage_prepared_proposal_validation(goal_id, proposal.version_id, owner_id)
            )
        assert run.status == "READY"
        run_id = run.id
        session.commit()
        repository.get_by_id_for_update(goal_id)
        with pytest.raises(GoalProposalConflict, match="no longer passes deterministic validation"):
            validator.require_ready_proposal_validation(goal_id, proposal.version_id, owner_id, run_id)


@pytest.mark.integration
def test_staged_validation_is_owned_by_outer_transaction(goal_version_engine, monkeypatch):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="stage-validation")
        session.commit()

        class NormalLLM:
            async def generate(self, _request):
                return LLMResponse(
                    content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
                )

        validator = GoalValidationRunService(session, NormalLLM())
        run = asyncio.run(
            validator.stage_prepared_proposal_validation(goal_id, proposal.version_id, owner_id)
        )
        with Session(goal_version_engine) as reader:
            assert reader.get(app.db.models.GoalValidationRunDB, run.id) is None
        session.rollback()
        assert session.get(app.db.models.GoalValidationRunDB, run.id) is None

        original_create = validator.repository.create

        def fail_after_flush(value):
            original_create(value)
            raise RuntimeError("Injected validation persistence failure")

        with monkeypatch.context() as patch:
            patch.setattr(validator.repository, "create", fail_after_flush)
            with pytest.raises(RuntimeError, match="Injected validation persistence failure"):
                asyncio.run(
                    validator.stage_prepared_proposal_validation(
                        goal_id, proposal.version_id, owner_id
                    )
                )
        session.commit()
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalValidationRunDB).where(
                app.db.models.GoalValidationRunDB.goal_version_id == proposal.version_id
            )
        ) == 0

        committed = asyncio.run(
            validator.stage_prepared_proposal_validation(goal_id, proposal.version_id, owner_id)
        )
        committed_id = committed.id
        session.commit()
    with Session(goal_version_engine) as reader:
        assert reader.get(app.db.models.GoalValidationRunDB, committed_id).goal_version_id == proposal.version_id


@pytest.mark.integration
def test_staged_validation_rejects_proposal_changed_during_provider_call(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="first-for-stage")
        session.commit()

        class ChangingLLM:
            async def generate(self, _request):
                with Session(goal_version_engine) as writer:
                    _stage_text(
                        writer, owner_id, goal_id, base_id,
                        key="newer-for-stage", revision=1, title="Newer proposal",
                    )
                    writer.commit()
                return LLMResponse(
                    content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
                )

        with pytest.raises(GoalProposalConflict, match="superseded"):
            asyncio.run(
                GoalValidationRunService(session, ChangingLLM()).stage_prepared_proposal_validation(
                    goal_id, proposal.version_id, owner_id
                )
            )
        session.commit()
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalValidationRunDB).where(
                app.db.models.GoalValidationRunDB.goal_version_id == proposal.version_id
            )
        ) == 0


@pytest.mark.integration
def test_staged_validation_checks_owner_and_isolation_before_provider(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="stage-auth")
        session.commit()

    class UnexpectedLLM:
        async def generate(self, _request):
            raise AssertionError("Invalid validation requests must not reach the provider")

    with Session(goal_version_engine) as session:
        with pytest.raises(ValueError, match="Goal proposal not found"):
            asyncio.run(
                GoalValidationRunService(session, UnexpectedLLM()).stage_prepared_proposal_validation(
                    goal_id, proposal.version_id, "other-user"
                )
            )
    with goal_version_engine.connect().execution_options(isolation_level="SERIALIZABLE") as connection:
        with Session(connection) as session:
            with pytest.raises(RuntimeError, match="requires READ COMMITTED"):
                asyncio.run(
                    GoalValidationRunService(session, UnexpectedLLM()).stage_prepared_proposal_validation(
                        goal_id, proposal.version_id, owner_id
                    )
                )


@pytest.mark.integration
def test_staged_validation_holds_goal_lock_until_outer_commit(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    attempted = Event()
    with Session(goal_version_engine) as session:
        proposal = _stage_text(session, owner_id, goal_id, base_id, key="lock-validation")
        session.commit()

        class NormalLLM:
            async def generate(self, _request):
                return LLMResponse(
                    content=json.dumps({"issues": []}), model="test-model", provider="test-provider"
                )

        asyncio.run(
            GoalValidationRunService(session, NormalLLM()).stage_prepared_proposal_validation(
                goal_id, proposal.version_id, owner_id
            )
        )

        def update():
            with Session(goal_version_engine) as writer:
                @event.listens_for(writer.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        attempted.set()

                result = _stage_text(
                    writer, owner_id, goal_id, base_id,
                    key="after-validation", revision=1, title="Changed proposal",
                )
                writer.commit()
                return result

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(update)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                session.commit()
                assert pending.result(timeout=10).revision == 2
            finally:
                session.rollback()


@pytest.mark.integration
def test_legacy_proposal_validation_rejects_head_changed_after_selection(goal_version_engine, monkeypatch):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        first = _stage_text(session, owner_id, goal_id, base_id, key="selected")
        session.commit()

        class UnexpectedLLM:
            async def generate(self, _request):
                raise AssertionError("Superseded proposals must not reach validation")

        validator = GoalValidationRunService(session, UnexpectedLLM())
        original_selection = validator.goal_repository.get_latest_proposal_version

        def select_then_supersede(selected_goal_id):
            selected = original_selection(selected_goal_id)
            with Session(goal_version_engine) as writer:
                _stage_text(
                    writer, owner_id, goal_id, base_id,
                    key="superseding", revision=1, title="Newer proposal",
                )
                writer.commit()
            return selected

        monkeypatch.setattr(validator.goal_repository, "get_latest_proposal_version", select_then_supersede)
        with pytest.raises(GoalProposalConflict, match="superseded"):
            asyncio.run(validator.validate_proposal(goal_id, first.version_id, owner_id))
        assert session.scalar(
            select(func.count()).select_from(app.db.models.GoalValidationRunDB).where(
                app.db.models.GoalValidationRunDB.goal_version_id == first.version_id
            )
        ) == 0


@pytest.mark.integration
def test_date_proposal_checks_merged_range_and_preserves_live_dates(goal_version_engine):
    owner_id, goal_id, _ = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        repository = GoalRepository(session)
        goal = repository.update(
            goal_id,
            {"start_date": date(2026, 1, 1), "end_date": date(2026, 12, 31)},
            owner_id,
        )
        base_id = repository.get_latest_version(goal_id).id
        goal.operative_goal_version_id = base_id
        session.commit()

        service = GoalDefinitionProposalService(session)
        arguments = {
            "goal_id": goal_id,
            "actor_user_id": owner_id,
            "expected_base_version_id": base_id,
            "expected_relationship_revision": 0,
        }
        with pytest.raises(ValueError, match="before start"):
            service.stage_proposal(
                **arguments,
                idempotency_key="invalid",
                expected_proposal_revision=0,
                changes=GoalProposalChanges(start_date=date(2027, 1, 1)),
            )
        session.rollback()
        assert session.get(app.db.models.GoalDefinitionProposalHeadDB, goal_id) is None
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "invalid")
        ) is None

        proposal = service.stage_proposal(
            **arguments,
            idempotency_key="valid",
            expected_proposal_revision=0,
            changes=GoalProposalChanges(end_date=date(2027, 2, 1)),
        )
        session.commit()
        candidate = session.get(app.db.models.GoalVersionDB, proposal.version_id)
        assert candidate.content["start_date"] == "2026-01-01"
        assert candidate.content["end_date"] == "2027-02-01"
        current = repository.get_by_id(goal_id)
        assert current.start_date == date(2026, 1, 1)
        assert current.end_date == date(2026, 12, 31)
        assert current.operative_goal_version_id == base_id

        cleared = service.stage_proposal(
            **arguments,
            idempotency_key="clear",
            expected_proposal_revision=1,
            changes=GoalProposalChanges(start_date=None),
        )
        session.commit()
        assert session.get(app.db.models.GoalVersionDB, cleared.version_id).content["start_date"] is None


@pytest.mark.integration
def test_structured_proposal_merges_patch_without_mutating_current_goal(goal_version_engine):
    owner_id, goal_id, base_id = _create_selected_baseline(goal_version_engine)
    with Session(goal_version_engine) as session:
        service = GoalDefinitionProposalService(session)
        arguments = {
            "goal_id": goal_id,
            "actor_user_id": owner_id,
            "expected_base_version_id": base_id,
            "expected_relationship_revision": 0,
        }
        noop = service.stage_proposal(
            **arguments,
            idempotency_key="empty-default",
            expected_proposal_revision=0,
            changes=GoalProposalChanges(structured_fields={"deliverables": []}),
        )
        assert noop.outcome == "NO_CHANGE"
        session.commit()
        proposal = service.stage_proposal(
            **arguments,
            idempotency_key="structured",
            expected_proposal_revision=0,
            changes=GoalProposalChanges(structured_fields={
                "outcome": "Improve reliability",
                "deliverables": ["Release plan"],
            }),
        )
        session.commit()
        candidate = session.get(app.db.models.GoalVersionDB, proposal.version_id)
        assert candidate.content["structured_fields"] == {
            "outcome": "Improve reliability",
            "deliverables": ["Release plan"],
        }
        assert GoalRepository(session).get_by_id(goal_id).structured_fields == {}
        assert candidate.content["criterion_versions"] == []

        whitespace = service.stage_proposal(
            **arguments,
            idempotency_key="whitespace",
            expected_proposal_revision=1,
            changes=GoalProposalChanges(structured_fields={"outcome": "Improve  reliability"}),
        )
        assert whitespace.outcome == "NO_CHANGE"
        assert whitespace.version_id == proposal.version_id
        session.commit()
        with pytest.raises(ValueError, match="deferred requirements"):
            service.stage_proposal(
                **arguments,
                idempotency_key="deferral",
                expected_proposal_revision=1,
                changes=GoalProposalChanges(structured_fields={
                    "deferred_requirements": [{
                        "requirement": "target",
                        "reason": "Await planning",
                        "resolution_stage": "Planning",
                    }]
                }),
            )
        session.rollback()
        assert session.get(
            app.db.models.GoalCommandReceiptDB, (owner_id, "PREPARE_DEFINITION", "deferral")
        ) is None


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
            GoalDefinitionProposalService(session).stage_proposal(
                goal_id=goal_id,
                actor_user_id=owner_id,
                idempotency_key="relationship",
                expected_base_version_id=base_id,
                expected_proposal_revision=0,
                expected_relationship_revision=1,
                changes=GoalProposalChanges(title="Revised goal"),
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
@pytest.mark.parametrize("concurrent_change", ["retire", "add_version"])
def test_criterion_writer_refreshes_preloaded_state_after_goal_lock(
    goal_version_engine, concurrent_change
):
    owner_id, goal_id = _create_committed_goal(goal_version_engine)
    original = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Deploy the release",
        completion_conditions="The release is available.",
    )
    changed = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Deploy the revised release",
        completion_conditions="The revised release is available.",
    )
    with Session(goal_version_engine) as session:
        criterion_id = GoalCriteriaService(session).create_manual(
            goal_id, owner_id, GoalCriterionCreateRequest(definition=original)
        ).id

    attempted = Event()
    with Session(goal_version_engine) as first:
        assert GoalRepository(first).get_by_id_for_update(goal_id) is not None

        def update():
            with Session(goal_version_engine) as session:
                service = GoalCriteriaService(session)
                stale = service.repository.get_by_id_and_goal(criterion_id, goal_id)
                assert not stale.is_retired
                assert len(stale.versions) == 1

                @event.listens_for(session.connection(), "before_cursor_execute")
                def signal_lock(_conn, _cursor, statement, _parameters, _context, _executemany):
                    if "FOR UPDATE" in statement.upper():
                        attempted.set()

                request = GoalCriterionUpdateRequest(definition=changed)
                if concurrent_change == "retire":
                    with pytest.raises(ValueError, match="Criterion not found"):
                        service.add_version(goal_id, criterion_id, owner_id, request)
                    return None
                _, version = service.add_version(goal_id, criterion_id, owner_id, request)
                return version.version

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(update)
            try:
                assert attempted.wait(10)
                assert not pending.done()
                service = GoalCriteriaService(first)
                if concurrent_change == "retire":
                    service.retire(goal_id, criterion_id, owner_id)
                else:
                    service.add_version(
                        goal_id, criterion_id, owner_id, GoalCriterionUpdateRequest(definition=changed)
                    )
                assert pending.result(timeout=10) == (
                    None if concurrent_change == "retire" else 3
                )
            finally:
                first.rollback()
    with Session(goal_version_engine) as verification:
        criterion = GoalCriteriaService(verification).repository.get_by_id(criterion_id)
        assert criterion.is_retired is (concurrent_change == "retire")
        assert len(criterion.versions) == (1 if concurrent_change == "retire" else 3)


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
