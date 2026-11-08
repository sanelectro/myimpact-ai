from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.v1.goals import update_goal
from app.models.api_v1_goals import GoalUpdateRequest
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus


def test_update_serializes_deferral_dates_without_changing_other_date_types():
    now = datetime.now(UTC)
    goal = SimpleNamespace(
        id="goal-1",
        user_id="owner-1",
        title="Goal",
        description=None,
        scope=GoalScope.PERSONAL,
        status=GoalStatus.DRAFT,
        sub_status=GoalSubStatus.NEEDS_REVIEW,
        created_at=now,
        updated_at=now,
        structured_fields={},
    )
    service = MagicMock()
    service.get_goal_by_id.return_value = goal
    service.update_goal.return_value = goal
    request = GoalUpdateRequest.model_validate({
        "start_date": "2026-11-08",
        "structured_fields": {
            "deferred_requirements": [{
                "requirement": "target",
                "reason": "Await agreement",
                "due_date": "2026-12-01",
            }]
        },
    })

    update_goal("goal-1", request, "owner-1", service)

    updates = service.update_goal.call_args.args[1]
    assert updates["start_date"].isoformat() == "2026-11-08"
    assert updates["structured_fields"]["deferred_requirements"][0]["due_date"] == "2026-12-01"
