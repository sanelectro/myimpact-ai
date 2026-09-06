from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.goal import GoalDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.repositories.goal import GoalRepository
from app.repositories.user import UserRepository


@pytest.mark.integration
def test_create_and_get_goal():
    goal_id = f"test-{uuid4()}"
    user_id = f"test-user-{uuid4()}"

    session = SessionLocal()

    try:
        user_repository = UserRepository(session)
        goal_repository = GoalRepository(session)

        user_repository.create(
            user_id=user_id,
            name="Integration Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
        )

        session.commit()

        created_goal = goal_repository.create(
            goal_id=goal_id,
            user_id=user_id,
            title="Integration Test Goal",
            description="Test goal description",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            source="integration-test",
        )

        session.commit()

        assert created_goal.id == goal_id
        assert created_goal.user_id == user_id
        assert created_goal.title == "Integration Test Goal"

        goal_by_id = goal_repository.get_by_id(goal_id)

        assert goal_by_id is not None
        assert goal_by_id.id == goal_id

        goals_by_user = goal_repository.get_by_user_id(user_id)

        assert len(goals_by_user) == 1
        assert goals_by_user[0].id == goal_id

    finally:
        session.execute(
            delete(GoalDB).where(GoalDB.id == goal_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()