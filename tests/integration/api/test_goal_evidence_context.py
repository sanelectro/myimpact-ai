from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from app.db.models.goal_version import GoalVersionDB
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.models.evidence_mapping import EvidenceRelevance
from app.repositories.evidence_mapping import EvidenceMappingRepository
from app.services.evidence_mapping import EvidenceMappingService
from tests.integration.api.test_goal_hierarchy import hierarchy_stack


@pytest.mark.integration
def test_context_deduplicates_origins_without_creating_parent_mappings(hierarchy_stack, monkeypatch):
    client, engine, owner, other, goals = hierarchy_stack
    root, child, grandchild, _, _, _ = goals
    params = {"user_id": owner}
    for goal, parent in ((child, root), (grandchild, child)):
        response = client.put(
            f"/api/v1/goals/{goal}/parent", params=params,
            json={"parent_goal_id": parent, "expected_revision": 0},
        )
        assert response.status_code == 200, response.text

    shared, contribution, new_evidence, private = (str(uuid4()) for _ in range(4))
    mappings = [str(uuid4()) for _ in range(3)]
    with Session(engine) as db:
        version_id = db.scalars(
            select(GoalVersionDB.id).where(GoalVersionDB.goal_id == root)
        ).one()
        db.execute(text("UPDATE goals SET status = 'ACTIVE', sub_status = 'ON_TRACK' WHERE id = :id"), {"id": root})
        db.execute(text("""
            INSERT INTO goal_validation_runs
                (id, goal_id, goal_version_id, status, findings, rule_set_version, prompt_version, created_at)
            VALUES (:id, :goal_id, :version_id, 'READY', '[]', 'test', 'test', now())
        """), {"id": str(uuid4()), "goal_id": root, "version_id": version_id})
        db.execute(text("""
            INSERT INTO goal_version_approvals (id, goal_id, goal_version_id, actor_user_id, created_at)
            VALUES (:id, :goal_id, :version_id, :owner, now())
        """), {"id": str(uuid4()), "goal_id": root, "version_id": version_id, "owner": owner})
        for evidence_id, evidence_owner in (
            (shared, owner), (contribution, owner), (new_evidence, owner), (private, other)
        ):
            db.execute(text("""
                INSERT INTO evidence
                    (id, user_id, source_type, title, captured_at, status, created_at, updated_at)
                VALUES (:id, :owner, 'PERSONAL', :id, now(), 'ACTIVE', now(), now())
            """), {"id": evidence_id, "owner": evidence_owner})
        for mapping_id, evidence_id, source_goal, kind in (
            (mappings[0], shared, root, "PRIMARY"),
            (mappings[1], shared, grandchild, "PRIMARY"),
            (mappings[2], contribution, child, "CONTRIBUTION"),
        ):
            db.execute(text("""
                INSERT INTO evidence_mappings
                    (id, evidence_id, goal_id, relevance, confidence, mapping_kind, created_at, updated_at)
                VALUES (:id, :evidence_id, :goal_id, 'HIGH', 1, :kind, now(), now())
            """), {"id": mapping_id, "evidence_id": evidence_id, "goal_id": source_goal, "kind": kind})
        db.commit()

    unowned = client.post(
        f"/api/v1/goals/{root}/evidence-links", params=params,
        json={"evidence_id": private, "relevance": "high"},
    )
    assert unowned.status_code == 404
    linked = client.post(
        f"/api/v1/goals/{root}/evidence-links", params=params,
        json={"evidence_id": new_evidence, "relevance": "high", "mapping_kind": "CONTRIBUTION",
              "contribution_description": "Supports this outcome"},
    )
    assert linked.status_code == 201, linked.text
    linked_mapping = linked.json()["mapping_id"]
    assert linked.json()["approval_status"] == "pending"
    duplicate = client.post(
        f"/api/v1/goals/{root}/evidence-links", params=params,
        json={"evidence_id": new_evidence, "relevance": "high"},
    )
    assert duplicate.status_code == 409

    direct = client.get(f"/api/v1/goals/{root}/evidence", params=params)
    assert direct.status_code == 200
    assert {item["evidence_id"] for item in direct.json()} == {shared, new_evidence}
    context = client.get(f"/api/v1/goals/{root}/evidence-context", params=params)
    assert context.status_code == 200, context.text
    items = {item["evidence_id"]: item for item in context.json()["items"]}
    assert set(items) == {shared, contribution, new_evidence}
    assert {origin["mapping_id"] for origin in items[shared]["origins"]} == {mappings[0], mappings[1]}
    assert {origin["origin"] for origin in items[shared]["origins"]} == {"DIRECT", "INHERITED"}
    inherited = next(origin for origin in items[shared]["origins"] if origin["origin"] == "INHERITED")
    assert inherited["goal_path"] == [root, child, grandchild]
    assert items[contribution]["origins"][0]["mapping_kind"] == "CONTRIBUTION"
    assert items[new_evidence]["origins"][0]["approval_status"] == "pending"

    first_page = client.get(f"/api/v1/goals/{root}/evidence-context", params={**params, "limit": 1})
    assert first_page.json()["has_more"] is True
    next_page = client.get(
        f"/api/v1/goals/{root}/evidence-context", params={**params, "limit": 1, "offset": 1}
    )
    assert first_page.json()["items"][0]["evidence_id"] != next_page.json()["items"][0]["evidence_id"]
    shallow = client.get(f"/api/v1/goals/{root}/evidence-context", params={**params, "max_depth": 0})
    assert shallow.json()["hierarchy_truncated"] is True
    assert {item["evidence_id"] for item in shallow.json()["items"]} == {shared, new_evidence}
    monkeypatch.setattr("app.services.goal_evidence_context.MAX_CONTEXT_GOALS", 2)
    bounded = client.get(f"/api/v1/goals/{root}/evidence-context", params=params)
    assert bounded.json()["hierarchy_truncated"] is True
    monkeypatch.setattr("app.services.goal_evidence_context.MAX_CONTEXT_GOALS", 1000)

    disconnect = client.request(
        "DELETE", f"/api/v1/goals/{child}/parent", params=params, json={"expected_revision": 1},
    )
    assert disconnect.status_code == 200
    after = client.get(f"/api/v1/goals/{root}/evidence-context", params=params)
    assert {item["evidence_id"] for item in after.json()["items"]} == {shared, new_evidence}
    with Session(engine) as db:
        assert db.execute(text(
            "SELECT count(*) FROM evidence_mappings WHERE id IN :ids"
        ).bindparams(bindparam("ids", expanding=True)),
            {"ids": [*mappings, linked_mapping]}).scalar_one() == 4
        assert db.execute(text(
            "SELECT count(*) FROM evidence_approvals WHERE mapping_id = :id AND status = 'PENDING'"
        ), {"id": linked_mapping}).scalar_one() == 1


@pytest.mark.integration
def test_concurrent_duplicate_links_create_one_mapping_and_approval(hierarchy_stack, monkeypatch):
    _, engine, owner, _, goals = hierarchy_stack
    evidence_id, goal_id = str(uuid4()), goals[0]
    with Session(engine) as db:
        db.execute(text("""
            INSERT INTO evidence
                (id, user_id, source_type, title, captured_at, status, created_at, updated_at)
            VALUES (:id, :owner, 'PERSONAL', 'Concurrent', now(), 'ACTIVE', now(), now())
        """), {"id": evidence_id, "owner": owner})
        db.commit()

    barrier = Barrier(2, timeout=10)
    original = EvidenceMappingRepository.get_by_evidence_and_goal

    def synchronized_lookup(self, evidence_id, goal_id):
        result = original(self, evidence_id, goal_id)
        barrier.wait()
        return result

    monkeypatch.setattr(EvidenceMappingRepository, "get_by_evidence_and_goal", synchronized_lookup)

    def create():
        with Session(engine) as db:
            try:
                EvidenceMappingService(db).create_mapping(
                    evidence_id=evidence_id, goal_id=goal_id,
                    relevance=EvidenceRelevance.HIGH, confidence=1.0,
                )
                return "created"
            except EvidenceMappingAlreadyExistsError:
                return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(lambda _: create(), range(2))) == ["created", "duplicate"]
    with Session(engine) as db:
        assert db.execute(text("""
            SELECT count(*) FROM evidence_mappings m
            JOIN evidence_approvals a ON a.mapping_id = m.id
            WHERE m.evidence_id = :evidence_id AND m.goal_id = :goal_id AND a.status = 'PENDING'
        """), {"evidence_id": evidence_id, "goal_id": goal_id}).scalar_one() == 1
