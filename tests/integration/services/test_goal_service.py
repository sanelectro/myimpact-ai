from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.goal import GoalCreate
from app.models.user import UserCreate
from app.services.goal import GoalService
from app.services.user import UserService


@pytest.mark.integration
def test_create_and_get_goal():
    session = SessionLocal()
    user_id = None
    goal_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Goal Service User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        service = GoalService(session)
        goal = service.create_goal(
            GoalCreate(
                user_id=user_id,
                title="Improve reliability",
                description="Improve deployment reliability.",
            )
        )
        goal_id = goal.id

        result = service.get_goal_by_id(goal_id)

        assert result is not None
        assert result.id == goal_id
        assert result.user_id == user_id
        assert result.title == "Improve reliability"

    finally:
        if goal_id is not None:
            session.execute(delete(GoalDB).where(GoalDB.id == goal_id))
        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()
