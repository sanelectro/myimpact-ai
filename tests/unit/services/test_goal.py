from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.models.goal import GoalCreate, GoalScope, GoalStatus, GoalSubStatus
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
        sub_status=GoalSubStatus.ON_TRACK,
        scope=GoalScope.TEAM,
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
        sub_status=GoalSubStatus.ON_TRACK,
        scope=GoalScope.TEAM,
        source=None,
        source_document_id=None,
    )
    session.commit.assert_called_once()


def test_create_organization_goal_uses_users_company():
    session = MagicMock(spec=Session)
    session.get.return_value = MagicMock(organization_id="org-123")
    repository = MagicMock(spec=GoalRepository)
    repository.create.return_value = MagicMock(spec=GoalDB)
    service = GoalService(session)
    service.repository = repository

    goal_data = GoalCreate(
        user_id="user-1",
        title="Improve reliability",
        scope=GoalScope.ORGANIZATION,
    )

    service.create_goal(goal_data)

    assert repository.create.call_args.kwargs["organization_id"] == "org-123"


def test_create_organization_goal_requires_company_profile():
    session = MagicMock(spec=Session)
    session.get.return_value = MagicMock(organization_id=None)
    repository = MagicMock(spec=GoalRepository)
    service = GoalService(session)
    service.repository = repository

    goal_data = GoalCreate(
        user_id="user-1",
        title="Improve reliability",
        scope=GoalScope.ORGANIZATION,
    )

    try:
        service.create_goal(goal_data)
    except ValueError as exc:
        assert "profile" in str(exc)
    else:
        raise AssertionError("Expected organization goal without company to fail")
    repository.create.assert_not_called()


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


def test_deactivate_goal_archives_with_normalized_reason():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    goal = MagicMock(spec=GoalDB)
    goal.status = GoalStatus.ACTIVE
    repository.get_by_id.return_value = goal
    repository.update.return_value = goal

    service = GoalService(session)
    service.repository = repository

    result = service.transition_status(
        "goal-123",
        GoalStatus.ARCHIVED,
        reason="  Priorities changed  ",
    )

    assert result is goal
    repository.update.assert_called_once_with(
        "goal-123",
        {
            "status": GoalStatus.ARCHIVED,
            "sub_status": GoalSubStatus.NONE,
            "deactivation_reason": "Priorities changed",
        },
    )
    session.commit.assert_called_once()


def test_deactivate_goal_requires_a_reason():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    goal = MagicMock(spec=GoalDB)
    goal.status = GoalStatus.ACTIVE
    repository.get_by_id.return_value = goal

    service = GoalService(session)
    service.repository = repository

    try:
        service.transition_status("goal-123", GoalStatus.ARCHIVED, reason="  ")
    except ValueError as exc:
        assert str(exc) == "A reason is required to deactivate a goal"
    else:
        raise AssertionError("Expected deactivation without a reason to fail")

    repository.update.assert_not_called()


def test_completed_goal_can_be_reopened_with_reason_and_history():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    goal = MagicMock(spec=GoalDB)
    goal.status = GoalStatus.COMPLETED
    repository.get_by_id.return_value = goal

    def update_goal(_goal_id, updates):
        goal.status = updates["status"]
        return goal

    repository.update.side_effect = update_goal

    service = GoalService(session)
    service.repository = repository

    result = service.transition_status(
        "goal-123",
        GoalStatus.ACTIVE,
        reason="The outcome needs further work",
        changed_by_user_id="user-1",
    )

    assert result is goal
    repository.update.assert_called_once_with(
        "goal-123",
        {"status": GoalStatus.ACTIVE, "sub_status": GoalSubStatus.ON_TRACK},
    )
    history = repository.add_status_history.call_args.args[0]
    assert history.from_status == GoalStatus.COMPLETED
    assert history.to_status == GoalStatus.ACTIVE
    assert history.reason == "The outcome needs further work"
    assert history.changed_by_user_id == "user-1"
    session.commit.assert_called_once()


def test_reopening_completed_goal_requires_a_reason():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=GoalRepository)
    goal = MagicMock(spec=GoalDB)
    goal.status = GoalStatus.COMPLETED
    repository.get_by_id.return_value = goal

    service = GoalService(session)
    service.repository = repository

    try:
        service.transition_status("goal-123", GoalStatus.ACTIVE, reason="  ")
    except ValueError as exc:
        assert str(exc) == "A reason is required to reopen a completed goal"
    else:
        raise AssertionError("Expected reopening without a reason to fail")

    repository.update.assert_not_called()
    repository.add_status_history.assert_not_called()
    session.commit.assert_not_called()
