from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.models.goal import GoalStatus, GoalSubStatus
from app.repositories.goal import GoalRepository
from app.services.goal import GoalService


def test_update_goal_commits():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.get_by_id.return_value = GoalDB(
        id="goal-1",
        user_id="user-1",
        title="Existing goal",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
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
    repository.get_by_id.return_value = GoalDB(
        id="goal-1",
        user_id="user-1",
        title="Archived goal",
        status=GoalStatus.ARCHIVED,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    repository.delete.return_value = True
    service = GoalService(session)
    service.repository = repository
    service.delete_goal("goal-1")
    repository.delete.assert_called_once_with("goal-1")
    session.commit.assert_called_once()


def test_delete_goal_rejects_non_archived_goal():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.get_by_id.return_value = GoalDB(
        id="goal-1",
        user_id="user-1",
        title="Active goal",
        status=GoalStatus.ACTIVE,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    service = GoalService(session)
    service.repository = repository

    with pytest.raises(ValueError, match="Only archived goals can be deleted"):
        service.delete_goal("goal-1")

    repository.delete.assert_not_called()
    session.commit.assert_not_called()


def test_status_transition_to_approved():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.get_by_id.return_value = GoalDB(
        id="goal-1", user_id="user-1", title="Existing goal",
        status=GoalStatus.DRAFT, sub_status=GoalSubStatus.NEEDS_REVIEW,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    repository.update.return_value = MagicMock(spec=GoalDB)
    service = GoalService(session)
    service.repository = repository

    service.update_goal("goal-1", {"status": GoalStatus.APPROVED, "sub_status": GoalSubStatus.NOT_STARTED})

    repository.update.assert_called_once_with(
        "goal-1", {"status": GoalStatus.APPROVED, "sub_status": GoalSubStatus.NOT_STARTED}
    )


def test_invalid_status_transition_is_rejected():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    repository.get_by_id.return_value = GoalDB(
        id="goal-1", user_id="user-1", title="Existing goal",
        status=GoalStatus.DRAFT, sub_status=GoalSubStatus.NEEDS_REVIEW,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    service = GoalService(session)
    service.repository = repository

    with pytest.raises(ValueError, match="Invalid goal status transition"):
        service.update_goal(
            "goal-1", {"status": GoalStatus.COMPLETED, "sub_status": GoalSubStatus.COMPLETED}
        )
