from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.models.goal import GoalCreate, GoalStatus
from app.repositories.goal import GoalRepository
from app.services.goal import GoalService


def test_create_goal():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.create.return_value = MagicMock(spec=GoalDB)

    service = GoalService(session)
    service.repository = repository

    goal_data = GoalCreate(
        user_id="user-1",
        title="Improve reliability",
        description="Improve deployment reliability.",
        status=GoalStatus.ACTIVE,
    )

    with patch("app.services.goal.uuid4", return_value="goal-123"):
        result = service.create_goal(goal_data)

    assert isinstance(result, GoalDB)
    repository.create.assert_called_once_with(
        goal_id="goal-123",
        user_id="user-1",
        title="Improve reliability",
        description="Improve deployment reliability.",
        start_date=None,
        end_date=None,
        status=GoalStatus.ACTIVE,
        source=None,
    )
    session.commit.assert_called_once()


def test_get_goal_by_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    expected = MagicMock(spec=GoalDB)
    repository.get_by_id.return_value = expected

    service = GoalService(session)
    service.repository = repository

    assert service.get_goal_by_id("goal-123") is expected
    repository.get_by_id.assert_called_once_with("goal-123")
    session.commit.assert_not_called()


def test_get_goal_by_id_returns_none():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.get_by_id.return_value = None

    service = GoalService(session)
    service.repository = repository

    assert service.get_goal_by_id("missing-goal") is None
    repository.get_by_id.assert_called_once_with("missing-goal")


def test_get_goals_by_user_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    expected = [MagicMock(spec=GoalDB), MagicMock(spec=GoalDB)]
    repository.get_by_user_id.return_value = expected

    service = GoalService(session)
    service.repository = repository

    assert service.get_goals_by_user_id("user-123") == expected
    repository.get_by_user_id.assert_called_once_with("user-123")
