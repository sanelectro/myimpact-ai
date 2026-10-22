import pytest

from app.models.goal import (
    VALID_SUB_STATUSES_BY_GOAL_STATUS,
    GoalCreate,
    GoalStatus,
    GoalSubStatus,
)


def test_default_goal_is_draft_and_needs_review():
    goal = GoalCreate(user_id="user-1", title="Improve reliability")
    assert goal.status is GoalStatus.DRAFT
    assert goal.sub_status is GoalSubStatus.NEEDS_REVIEW


def test_active_goal_defaults_to_on_track():
    goal = GoalCreate(user_id="user-1", title="Improve reliability", status=GoalStatus.ACTIVE)
    assert goal.sub_status is GoalSubStatus.ON_TRACK


def test_approved_goal_requires_not_started_substatus():
    goal = GoalCreate(
        user_id="user-1",
        title="Improve reliability",
        status=GoalStatus.APPROVED,
        sub_status=GoalSubStatus.NOT_STARTED,
    )
    assert goal.status is GoalStatus.APPROVED
    assert goal.sub_status is GoalSubStatus.NOT_STARTED


def test_invalid_lifecycle_pair_is_rejected():
    with pytest.raises(ValueError, match="Invalid goal status/sub-status combination"):
        GoalCreate(
            user_id="user-1",
            title="Improve reliability",
            status=GoalStatus.APPROVED,
            sub_status=GoalSubStatus.ON_TRACK,
        )


def test_every_lifecycle_and_sub_status_pair_matches_the_allowed_matrix():
    for status in GoalStatus:
        for sub_status in GoalSubStatus:
            if sub_status in VALID_SUB_STATUSES_BY_GOAL_STATUS[status]:
                goal = GoalCreate(
                    user_id="user-1",
                    title="Check lifecycle pair",
                    status=status,
                    sub_status=sub_status,
                )
                assert goal.status is status
                assert goal.sub_status is sub_status
            else:
                with pytest.raises(
                    ValueError,
                    match="Invalid goal status/sub-status combination",
                ):
                    GoalCreate(
                        user_id="user-1",
                        title="Check lifecycle pair",
                        status=status,
                        sub_status=sub_status,
                    )
