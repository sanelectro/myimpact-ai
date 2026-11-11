from unittest.mock import Mock

import pytest

from app.models.milestone import MilestoneCreate
from app.services.milestone import MilestoneService


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("create_milestone", (MilestoneCreate(title="Milestone"),)),
        ("update_milestone", ("milestone-1", {"title": "Changed"})),
        ("archive_milestone", ("milestone-1",)),
        ("delete_archived_milestone", ("milestone-1",)),
    ],
)
def test_missing_goal_is_rejected_before_milestone_mutation(method, args):
    session = Mock()
    service = MilestoneService(session)
    service.goal_repository.get_by_id_for_update = Mock(return_value=None)
    service.repository = Mock()

    with pytest.raises(ValueError, match="Goal not found"):
        getattr(service, method)("missing-goal", *args)

    service.repository.create.assert_not_called()
    service.repository.get_by_id_and_goal.assert_not_called()
    service.repository.update.assert_not_called()
    service.repository.delete.assert_not_called()
    session.commit.assert_not_called()
