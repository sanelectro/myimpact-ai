import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, String, Table, create_engine, select, text
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, authorize_request_user, get_current_user
from app.db.base import Base
from app.db.models.goal import GoalDB
from app.db.models.goal_version import GoalVersionDB
from app.db.models.user import UserDB
from app.db.session import get_db
from app.main import app
from app.models.goal import GoalCreate
from app.services.goal import GoalService
from app.services.goal_hierarchy import GoalHierarchyService


@pytest.fixture
def hierarchy_stack():
    container = os.environ.get("HIERARCHY_TEST_CONTAINER")
    url = os.environ.get("HIERARCHY_TEST_DATABASE_URL")
    if not container or not url:
        pytest.skip("Requires an explicitly configured disposable hierarchy database")
    label = subprocess.run(
        ["docker", "inspect", "--format", '{{index .Config.Labels "myimpact.test"}}', container],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    port = subprocess.run(
        ["docker", "port", container, "5432/tcp"],
        capture_output=True, text=True, check=True,
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
    suffix = uuid4().hex
    owner, other = f"hierarchy-owner-{suffix}", f"hierarchy-other-{suffix}"
    now = datetime.now(UTC)
    with Session(engine) as db:
        for user_id in (owner, other):
            db.add(UserDB(
                id=user_id, name="Owner", email=f"{user_id}@example.test",
                created_at=now, updated_at=now,
            ))
        db.commit()
        goals = [
            GoalService(db).create_goal(GoalCreate(user_id=user_id, title=title)).id
            for user_id, title in (
                (owner, "A"), (owner, "B"), (owner, "C"),
                (owner, "D"), (owner, "E"), (other, "Private"),
            )
        ]

    def override_db():
        with Session(engine) as db:
            yield db

    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.pop(authorize_request_user, None)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        owner, "owner@example.test", None, {"myimpact-ai"}
    )
    try:
        with TestClient(app) as client:
            yield client, engine, owner, other, goals
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        engine.dispose()
        if team_table is not None:
            Base.metadata.remove(team_table)


@pytest.mark.integration
def test_create_with_parent_is_atomic_and_audited(hierarchy_stack):
    client, engine, owner, other, goals = hierarchy_stack
    parent, _, _, _, _, private = goals
    params = {"user_id": owner}
    created = client.post(
        "/api/v1/goals", params=params,
        json={"title": "Created with parent", "goal_level": "SPRINT", "parent_goal_id": parent},
    )
    assert created.status_code == 201, created.text
    goal = created.json()
    assert goal["parent_goal_id"] == parent
    assert goal["relationship_revision"] == 1
    assert goal["goal_level"] == "SPRINT"
    history = client.get(f"/api/v1/goals/{goal['id']}/relationship-history", params=params)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["old_parent_goal_id"] is None
    assert history.json()[0]["new_parent_goal_id"] == parent
    assert history.json()[0]["actor_user_id"] == owner
    assert history.json()[0]["relationship_revision"] == 1
    with Session(engine) as db:
        versions = db.scalars(select(GoalVersionDB).where(GoalVersionDB.goal_id == goal["id"])).all()
        assert len(versions) == 1
        assert versions[0].origin == "USER"
        assert "parent_goal_id" not in versions[0].content

    for parent_id in (private, "missing-parent"):
        title = f"Must roll back {parent_id}"
        failed = client.post(
            "/api/v1/goals", params=params,
            json={"title": title, "parent_goal_id": parent_id},
        )
        assert failed.status_code == 404, failed.text
        with Session(engine) as db:
            assert db.scalars(select(GoalDB).where(GoalDB.user_id == owner, GoalDB.title == title)).first() is None

    standalone = client.post(
        "/api/v1/goals", params=params, json={"title": "Standalone", "parent_goal_id": None},
    )
    assert standalone.status_code == 201, standalone.text
    assert standalone.json()["parent_goal_id"] is None
    assert standalone.json()["relationship_revision"] == 0
    assert client.get(
        f"/api/v1/goals/{standalone.json()['id']}/relationship-history", params=params,
    ).json() == []
    assert client.post(
        "/api/v1/goals", params=params, json={"title": "Invalid", "parent_goal_id": ""},
    ).status_code == 422


@pytest.mark.integration
def test_parent_deleted_during_create_rolls_back_goal(hierarchy_stack, monkeypatch):
    client, engine, owner, _, goals = hierarchy_stack
    parent = goals[3]
    entered, resume = Event(), Event()
    original = GoalHierarchyService.stage_initial_parent

    def wait_before_link(service, goal_id, user_id, parent_goal_id):
        entered.set()
        if not resume.wait(10):
            raise RuntimeError("Timed out waiting for concurrent parent deletion")
        return original(service, goal_id, user_id, parent_goal_id)

    monkeypatch.setattr(GoalHierarchyService, "stage_initial_parent", wait_before_link)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post, "/api/v1/goals",
            params={"user_id": owner}, json={"title": "Concurrent child", "parent_goal_id": parent},
        )
        try:
            assert entered.wait(10)
            with Session(engine) as db:
                db.execute(text("DELETE FROM goals WHERE id = :id"), {"id": parent})
                db.commit()
        finally:
            resume.set()
        response = future.result(timeout=15)
    assert response.status_code == 404, response.text
    with Session(engine) as db:
        assert db.scalars(select(GoalDB).where(
            GoalDB.user_id == owner, GoalDB.title == "Concurrent child"
        )).first() is None


@pytest.mark.integration
def test_hierarchy_mutations_history_and_ownership(hierarchy_stack):
    client, engine, owner, other, goals = hierarchy_stack
    a, b, c, _, _, private = goals
    params = {"user_id": owner}
    evidence_id, mapping_id, approval_id = (str(uuid4()) for _ in range(3))
    with Session(engine) as db:
        original = db.get(GoalDB, a)
        original_fields = (
            original.user_id, original.title, original.description, original.scope,
            original.goal_level, original.status, original.sub_status,
            original.structured_fields, original.updated_at,
        )
        version_id = db.scalars(
            select(GoalVersionDB.id).where(GoalVersionDB.goal_id == a)
        ).one()
        db.execute(text("""
            INSERT INTO evidence (id, user_id, source_type, title, captured_at, status, created_at, updated_at)
            VALUES (:id, :owner, 'PERSONAL', 'Evidence', now(), 'ACTIVE', now(), now())
        """), {"id": evidence_id, "owner": owner})
        db.execute(text("""
            INSERT INTO evidence_mappings (id, evidence_id, goal_id, relevance, confidence, created_at, updated_at)
            VALUES (:id, :evidence_id, :goal_id, 'HIGH', 1, now(), now())
        """), {"id": mapping_id, "evidence_id": evidence_id, "goal_id": a})
        db.execute(text("""
            INSERT INTO goal_version_approvals (id, goal_id, goal_version_id, actor_user_id, created_at)
            VALUES (:id, :goal_id, :version_id, :owner, now())
        """), {"id": approval_id, "goal_id": a, "version_id": version_id, "owner": owner})
        db.commit()

    def parent(child, target, revision, reason=None):
        return client.put(
            f"/api/v1/goals/{child}/parent", params=params,
            json={"parent_goal_id": target, "expected_revision": revision, "reason": reason},
        )

    response = parent(a, b, 0, "Alignment")
    assert response.status_code == 200, response.text
    assert response.json()["relationship_revision"] == 1
    assert parent(a, b, 1).json()["relationship_revision"] == 1
    assert parent(a, b, 0).status_code == 409
    assert parent(b, a, 0).status_code == 409
    assert parent(c, c, 0).status_code == 409
    assert parent(a, private, 1).status_code == 404
    assert parent(b, c, 0).status_code == 200
    assert parent(c, a, 0).status_code == 409

    hierarchy = client.get(f"/api/v1/goals/{a}/hierarchy", params=params)
    assert hierarchy.status_code == 200
    assert [item["id"] for item in hierarchy.json()["ancestors"]] == [b, c]
    limited = client.get(f"/api/v1/goals/{a}/hierarchy", params={**params, "limit": 1})
    assert limited.json()["next_ancestor_id"] == c
    children = client.get(f"/api/v1/goals/{b}/children", params=params)
    assert [item["id"] for item in children.json()] == [a]
    assert client.get(f"/api/v1/goals/{a}/hierarchy", params={"user_id": other}).status_code == 403

    assert parent(a, c, 1, "Reparent").json()["relationship_revision"] == 2
    disconnect = client.request(
        "DELETE", f"/api/v1/goals/{a}/parent", params=params,
        json={"expected_revision": 2, "reason": "Disconnect"},
    )
    assert disconnect.status_code == 200
    assert disconnect.json()["relationship_revision"] == 3
    no_op = client.request(
        "DELETE", f"/api/v1/goals/{a}/parent", params=params,
        json={"expected_revision": 3},
    )
    assert no_op.status_code == 200
    assert no_op.json()["relationship_revision"] == 3
    history = client.get(f"/api/v1/goals/{a}/relationship-history", params=params)
    assert [item["relationship_revision"] for item in history.json()] == [3, 2, 1]
    assert [item["reason"] for item in history.json()] == ["Disconnect", "Reparent", "Alignment"]
    assert all(item["actor_user_id"] == owner for item in history.json())

    with Session(engine) as db:
        stored = db.get(GoalDB, a)
        assert stored.status.value == "draft"
        assert stored.goal_level is None
        assert stored.parent_goal_id is None
        assert (
            stored.user_id, stored.title, stored.description, stored.scope,
            stored.goal_level, stored.status, stored.sub_status,
            stored.structured_fields, stored.updated_at,
        ) == original_fields
        assert len(db.scalars(select(GoalVersionDB).where(GoalVersionDB.goal_id == a)).all()) == 1
        assert db.execute(text(
            "SELECT goal_id FROM evidence_mappings WHERE id = :id"
        ), {"id": mapping_id}).scalar_one() == a
        assert db.execute(text(
            "SELECT goal_version_id FROM goal_version_approvals WHERE id = :id"
        ), {"id": approval_id}).scalar_one() == version_id
        archived_parent = db.get(GoalDB, c)
        from app.models.goal import GoalStatus, GoalSubStatus
        archived_parent.status = GoalStatus.ARCHIVED
        archived_parent.sub_status = GoalSubStatus.NONE
        db.commit()
    assert client.delete(f"/api/v1/goals/{c}", params=params).status_code == 409


@pytest.mark.integration
def test_concurrent_reverse_links_reject_one_cycle(hierarchy_stack):
    _, engine, owner, _, goals = hierarchy_stack
    first, second = goals[3:5]

    def connect(pair):
        child, target = pair
        with TestClient(app) as client:
            response = client.put(
                f"/api/v1/goals/{child}/parent", params={"user_id": owner},
                json={"parent_goal_id": target, "expected_revision": 0},
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(connect, [(first, second), (second, first)]))
    assert sorted(statuses) == [200, 409]
    with Session(engine) as db:
        linked = db.scalars(select(GoalDB).where(GoalDB.id.in_([first, second]))).all()
        assert sum(goal.parent_goal_id is not None for goal in linked) == 1

    child, left, right = goals[:3]
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(connect, [(child, left), (child, right)]))
    assert sorted(statuses) == [200, 409]
    with Session(engine) as db:
        assert db.get(GoalDB, child).relationship_revision == 1
