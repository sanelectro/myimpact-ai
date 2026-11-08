import pytest

from tests.integration.api.test_goal_hierarchy import hierarchy_stack


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
