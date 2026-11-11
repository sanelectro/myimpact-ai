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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.db.models
from app.db.models.team import TeamDB as _TeamDB
from app.db.models.user import UserDB
from app.models.llm import LLMResponse
from app.repositories.goal import GoalRepository
from app.services.goal_validation_runs import GoalValidationRunService


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
