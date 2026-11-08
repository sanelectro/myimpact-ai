import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.goal_version import GoalVersionDB
from tests.integration.api.test_goal_hierarchy import hierarchy_stack


@pytest.mark.integration
def test_legacy_client_update_preserves_deferrals_and_relationship(hierarchy_stack):
    client, engine, owner, _, goals = hierarchy_stack
    params = {"user_id": owner}
    created = client.post(
        "/api/v1/goals",
        params=params,
        json={
            "title": "Mixed-version child",
            "goal_level": "SPRINT",
            "parent_goal_id": goals[0],
            "structured_fields": {"deferred_requirements": [{
                "requirement": "target",
                "reason": "Await target",
                "resolution_stage": "Planning",
            }]},
        },
    )
    assert created.status_code == 201, created.text
    goal = created.json()
    goal_id = goal["id"]
    history = client.get(f"/api/v1/goals/{goal_id}/relationship-history", params=params).json()
    old_fields = dict(goal["structured_fields"])
    old_fields.pop("deferred_requirements")
    old_fields["outcome"] = "Updated by old client"

    updated = client.put(
        f"/api/v1/goals/{goal_id}", params=params, json={"structured_fields": old_fields},
    )
    assert updated.status_code == 200, updated.text
    result = updated.json()
    assert result["structured_fields"]["outcome"] == "Updated by old client"
    assert result["structured_fields"]["deferred_requirements"] == goal["structured_fields"]["deferred_requirements"]
    assert result["parent_goal_id"] == goals[0]
    assert result["relationship_revision"] == 1
    assert result["goal_level"] == "SPRINT"
    assert client.get(f"/api/v1/goals/{goal_id}/relationship-history", params=params).json() == history
    with Session(engine) as db:
        versions = db.scalars(
            select(GoalVersionDB).where(GoalVersionDB.goal_id == goal_id).order_by(GoalVersionDB.version)
        ).all()
        assert len(versions) == 2
        assert versions[-1].content["structured_fields"]["deferred_requirements"] == goal["structured_fields"]["deferred_requirements"]


@pytest.mark.integration
def test_stale_deferral_edit_conflicts_without_overwriting_other_change(hierarchy_stack):
    client, _, owner, _, goals = hierarchy_stack
    goal_id = goals[0]
    params = {"user_id": owner}
    original = client.get(f"/api/v1/goals/{goal_id}", params=params).json()["structured_fields"]
    target = {"requirement": "target", "reason": "Await target", "resolution_stage": "Planning"}
    baseline = {"requirement": "baseline", "reason": "Await baseline", "resolution_stage": "Planning"}
    first = client.put(
        f"/api/v1/goals/{goal_id}", params=params,
        json={"structured_fields": {**original, "deferred_requirements": [target]},
              "expected_deferred_requirements": []},
    )
    assert first.status_code == 200, first.text
    stale = client.put(
        f"/api/v1/goals/{goal_id}", params=params,
        json={"structured_fields": {**original, "deferred_requirements": [baseline]},
              "expected_deferred_requirements": []},
    )
    assert stale.status_code == 409, stale.text
    current = client.get(f"/api/v1/goals/{goal_id}", params=params).json()["structured_fields"]
    assert [item["requirement"] for item in current["deferred_requirements"]] == ["target"]
    retry = client.put(
        f"/api/v1/goals/{goal_id}", params=params,
        json={"structured_fields": {**current, "deferred_requirements": [*current["deferred_requirements"], baseline]},
              "expected_deferred_requirements": current["deferred_requirements"]},
    )
    assert retry.status_code == 200, retry.text
    assert {item["requirement"] for item in retry.json()["structured_fields"]["deferred_requirements"]} == {"baseline", "target"}
