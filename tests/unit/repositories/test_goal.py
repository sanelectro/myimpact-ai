from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.models.goal import GoalStatus
from app.repositories.goal import GoalRepository


def test_get_by_id_returns_goal():
    session = MagicMock(spec=Session)

    expected_goal = GoalDB(
        id="goal-1",
        user_id="user-1",
        title="Improve deployment reliability",
    )

    session.get.return_value = expected_goal

    repository = GoalRepository(session)

    result = repository.get_by_id("goal-1")

    assert result is expected_goal
    session.get.assert_called_once_with(GoalDB, "goal-1")


def test_get_by_id_returns_none_when_goal_not_found():
    session = MagicMock(spec=Session)
    session.get.return_value = None

    repository = GoalRepository(session)

    result = repository.get_by_id("missing-goal")

    assert result is None
    session.get.assert_called_once_with(GoalDB, "missing-goal")
    
def test_get_by_user_id_returns_goals():
    session = MagicMock(spec=Session)

    expected_goals = [
        GoalDB(
            id="goal-1",
            user_id="user-1",
            title="Improve deployment reliability",
        ),
        GoalDB(
            id="goal-2",
            user_id="user-1",
            title="Improve observability",
        ),
    ]

    session.query.return_value.filter.return_value.all.return_value = expected_goals

    repository = GoalRepository(session)

    result = repository.get_by_user_id("user-1")

    assert result == expected_goals


def test_get_by_user_id_returns_empty_list_when_no_goals():
    session = MagicMock(spec=Session)

    session.query.return_value.filter.return_value.all.return_value = []

    repository = GoalRepository(session)

    result = repository.get_by_user_id("user-1")

    assert result == []
    
    
def test_create_goal():
    session = MagicMock(spec=Session)

    repository = GoalRepository(session)

    result = repository.create(
        goal_id="goal-1",
        user_id="user-1",
        title="Improve deployment reliability",
        description="Reduce deployment-related incidents",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 12, 31),
        source="1:1",
    )

    assert isinstance(result, GoalDB)
    assert result.id == "goal-1"
    assert result.user_id == "user-1"
    assert result.title == "Improve deployment reliability"
    assert result.description == "Reduce deployment-related incidents"
    assert result.start_date == date(2026, 9, 1)
    assert result.end_date == date(2026, 12, 31)
    assert result.status == GoalStatus.ACTIVE
    assert result.source == "1:1"

    assert isinstance(result.created_at, datetime)
    assert result.created_at.tzinfo == UTC
    assert result.updated_at == result.created_at

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()