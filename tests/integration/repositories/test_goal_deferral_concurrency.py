import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from sqlalchemy import Column, String, Table, create_engine, event
from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.base import Base
from app.models.goal import GoalCreate
from app.repositories.goal import GoalRepository
from app.services.goal import GoalService


@pytest.mark.integration
def test_old_writer_preserves_concurrently_added_deferral():
    container = os.environ.get("HIERARCHY_TEST_CONTAINER")
    url = os.environ.get("HIERARCHY_TEST_DATABASE_URL")
    if not container or not url:
        pytest.skip("Requires an explicitly configured disposable hierarchy database")
    label = subprocess.run(
        ["docker", "inspect", "--format", '{{index .Config.Labels "myimpact.test"}}', container],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    port = subprocess.run(
        ["docker", "port", container, "5432/tcp"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    parsed = urlparse(url)
    if label != "hierarchy-disposable" or parsed.hostname != "127.0.0.1" or (
        port != f"127.0.0.1:{parsed.port}" or parsed.path != "/hierarchytest"
    ):
        raise RuntimeError("The test database must be the labelled disposable container")

    team_table = None
    if "teams" not in Base.metadata.tables:
        team_table = Table("teams", Base.metadata, Column("id", String(64), primary_key=True))
    engine = create_engine(url)
    owner = f"deferral-owner-{uuid4().hex}"
    now = datetime.now(UTC)
    try:
        with Session(engine) as setup:
            setup.add(UserDB(
                id=owner,
                name="Owner",
                email=f"{owner}@example.test",
                created_at=now,
                updated_at=now,
            ))
            setup.commit()
            goal = GoalService(setup).create_goal(GoalCreate(user_id=owner, title="Goal"))
            goal_id = goal.id

        with Session(engine) as writer, Session(engine) as old_writer:
            locked = GoalRepository(writer).get_by_id_for_update(goal_id)
            stale = old_writer.get(GoalDB, goal_id)
            old_fields = dict(stale.structured_fields)
            old_fields.pop("deferred_requirements", None)
            old_fields["outcome"] = "Updated by old client"
            started = Event()

            @event.listens_for(old_writer.connection(), "before_cursor_execute")
            def signal_lock_attempt(_conn, _cursor, statement, _parameters, _context, _executemany):
                if "FOR UPDATE" in statement.upper():
                    started.set()

            def save_old_payload():
                GoalService(old_writer).update_goal(
                    goal_id, {"structured_fields": old_fields}, changed_by_user_id=owner
                )

            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(save_old_payload)
                assert started.wait(timeout=5)
                assert not pending.done()
                new_fields = dict(locked.structured_fields)
                new_fields["deferred_requirements"] = [{
                    "requirement": "target", "reason": "Await agreement", "resolution_stage": "Planning"
                }]
                GoalService(writer).update_goal(
                    goal_id, {"structured_fields": new_fields}, changed_by_user_id=owner
                )
                pending.result(timeout=10)

        with Session(engine) as verification:
            stored = verification.get(GoalDB, goal_id)
            assert stored.structured_fields["outcome"] == "Updated by old client"
            assert stored.structured_fields["deferred_requirements"][0]["reason"] == "Await agreement"
    finally:
        engine.dispose()
        if team_table is not None:
            Base.metadata.remove(team_table)
