from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.repositories.goal import GoalRepository
from app.services.goal import GoalService


def test_update_goal_commits():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.update.return_value = MagicMock(spec=GoalDB)
    service = GoalService(session)
    service.repository = repository
    result = service.update_goal("goal-1", {"title": "Updated"})
    assert isinstance(result, GoalDB)
    repository.update.assert_called_once_with("goal-1", {"title": "Updated"})
    session.commit.assert_called_once()


def test_delete_goal_commits():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.delete.return_value = True
    service = GoalService(session)
    service.repository = repository
    service.delete_goal("goal-1")
    repository.delete.assert_called_once_with("goal-1")
    session.commit.assert_called_once()
