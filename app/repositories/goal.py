from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.db.models.goal_status_history import GoalStatusHistoryDB
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.repositories.base import BaseRepository


def _default_sub_status(status: GoalStatus) -> GoalSubStatus:
    return {
        GoalStatus.DRAFT: GoalSubStatus.NEEDS_REVIEW,
        GoalStatus.APPROVED: GoalSubStatus.NOT_STARTED,
        GoalStatus.ACTIVE: GoalSubStatus.ON_TRACK,
        GoalStatus.COMPLETED: GoalSubStatus.COMPLETED,
        GoalStatus.ARCHIVED: GoalSubStatus.NONE,
    }[status]


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
    
    def get_by_source_document_id(self, document_id: str) -> list[GoalDB]:
        return (
            self.session.query(GoalDB)
            .filter(GoalDB.source_document_id == document_id)
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
    status: GoalStatus = GoalStatus.DRAFT,
    sub_status: GoalSubStatus | None = None,
    source: str | None = None,
    source_document_id: str | None = None,
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
            sub_status=sub_status or _default_sub_status(status),
            source=source,
            source_document_id=source_document_id,
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

    def add_status_history(self, history: GoalStatusHistoryDB) -> None:
        self.session.add(history)
        self.session.flush()

    def get_status_history(self, goal_id: str) -> list[GoalStatusHistoryDB]:
        return (
            self.session.query(GoalStatusHistoryDB)
            .filter(GoalStatusHistoryDB.goal_id == goal_id)
            .order_by(GoalStatusHistoryDB.created_at.desc())
            .all()
        )

    def delete(self, goal_id: str) -> bool:
        goal = self.get_by_id(goal_id)
        if goal is None:
            return False
        self.session.delete(goal)
        self.session.flush()
        return True
