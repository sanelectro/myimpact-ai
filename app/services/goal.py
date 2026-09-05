from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.models.goal import GoalCreate
from app.repositories.goal import GoalRepository
from app.services.base import BaseService


class GoalService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = GoalRepository(session)

    def create_goal(self, goal_data: GoalCreate) -> GoalDB:
        goal = self.repository.create(
            goal_id=str(uuid4()),
            user_id=goal_data.user_id,
            title=goal_data.title,
            description=goal_data.description,
            start_date=goal_data.start_date,
            end_date=goal_data.end_date,
            status=goal_data.status,
            source=goal_data.source,
        )
        self.commit()
        return goal

    def get_goal_by_id(self, goal_id: str) -> GoalDB | None:
        return self.repository.get_by_id(goal_id)

    def get_goals_by_user_id(self, user_id: str) -> list[GoalDB]:
        return self.repository.get_by_user_id(user_id)
