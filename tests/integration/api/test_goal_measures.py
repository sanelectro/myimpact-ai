import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.integration.api.test_goal_hierarchy import hierarchy_stack


@pytest.mark.integration
def test_child_completion_does_not_infer_parent_outcome_or_impact(hierarchy_stack):
    client, engine, owner, other, goals = hierarchy_stack
    parent, child, second, unrelated, _, private = goals
    for goal in (child, second):
        response = client.put(
            f"/api/v1/goals/{goal}/parent", params={"user_id": owner},
            json={"parent_goal_id": parent, "expected_revision": 0},
        )
        assert response.status_code == 200, response.text
    with Session(engine) as db:
        db.execute(text("UPDATE goals SET status = 'COMPLETED' WHERE id IN (:a, :b, :c)"),
                   {"a": child, "b": second, "c": unrelated})
        db.commit()

    response = client.get(f"/api/v1/goals/{parent}/measures", params={"user_id": owner})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["child_execution"] == {"total": 2, "by_status": {"completed": 2}}
    assert data["own_criterion_assessment"]["goal_id"] == parent
    assert data["own_criterion_assessment"]["criteria_count"] == 0
    assert data["own_criterion_assessment"]["evidence_coverage_percentage"] is None
    assert data["outcome_achievement"] is None
    assert data["demonstrated_impact"] is None
    detached = client.request(
        "DELETE", f"/api/v1/goals/{child}/parent", params={"user_id": owner},
        json={"expected_revision": 1},
    )
    assert detached.status_code == 200
    after = client.get(f"/api/v1/goals/{parent}/measures", params={"user_id": owner}).json()
    assert after["child_execution"] == {"total": 1, "by_status": {"completed": 1}}
    empty = client.get(f"/api/v1/goals/{child}/measures", params={"user_id": owner}).json()
    assert empty["child_execution"] == {"total": 0, "by_status": {}}
    assert empty["outcome_achievement"] is None
    assert empty["demonstrated_impact"] is None
    assert client.get(f"/api/v1/goals/{private}/measures", params={"user_id": owner}).status_code == 404
    assert client.get(f"/api/v1/goals/{parent}/measures", params={"user_id": other}).status_code == 403
