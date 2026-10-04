from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.models.goal import GoalScope, GoalStatus
from app.repositories.base import BaseRepository


class GoalRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, goal_id: str) -> GoalDB | None:
        return self.session.get(GoalDB, goal_id)

    def get_by_user_id(self, user_id: str) -> list[GoalDB]:
        return (
            self.session.query(GoalDB)
            .filter(GoalDB.user_id == user_id)
            .all()
        )
    
    def create(
    self,
    *,
    goal_id: str,
    user_id: str,
    title: str,
    description: str | None = None,
    scope: GoalScope = GoalScope.PERSONAL,
    start_date: date | None = None,
    end_date: date | None = None,
    status: GoalStatus = GoalStatus.ACTIVE,
    source: str | None = None,
) -> GoalDB:
        now = datetime.now(UTC)

        goal = GoalDB(
            id=goal_id,
            user_id=user_id,
            title=title,
            description=description,
            scope=scope,
            start_date=start_date,
            end_date=end_date,
            status=status,
            source=source,
            created_at=now,
            updated_at=now,
        )

        self.session.add(goal)
        self.session.flush()

        return goal
    def update(self, goal_id: str, values: dict) -> GoalDB | None:
        goal = self.get_by_id(goal_id)
        if goal is None:
            return None
        for field, value in values.items():
            setattr(goal, field, value)
        goal.updated_at = datetime.now(UTC)
        self.session.flush()
        return goal

    def delete(self, goal_id: str) -> bool:
        goal = self.get_by_id(goal_id)
        if goal is None:
            return False
        self.session.delete(goal)
        self.session.flush()
        return True

