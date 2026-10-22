from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models.milestone import MilestoneDB
from app.models.milestone import MilestoneCreate
from app.repositories.base import BaseRepository


class MilestoneRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id_and_goal(self, milestone_id: str, goal_id: str) -> MilestoneDB | None:
        return (
            self.session.query(MilestoneDB)
            .filter(MilestoneDB.id == milestone_id, MilestoneDB.goal_id == goal_id)
            .one_or_none()
        )

    def get_by_goal_id(
        self,
        goal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[MilestoneDB]:
        query = self.session.query(MilestoneDB).filter(MilestoneDB.goal_id == goal_id)
        if not include_archived:
            query = query.filter(MilestoneDB.archived_at.is_(None))
        return query.order_by(MilestoneDB.created_at, MilestoneDB.id).all()

    def create(
        self,
        *,
        milestone_id: str,
        goal_id: str,
        values: MilestoneCreate,
    ) -> MilestoneDB:
        now = datetime.now(UTC)
        milestone = MilestoneDB(
            id=milestone_id,
            goal_id=goal_id,
            title=values.title,
            description=values.description,
            completion_criteria=values.completion_criteria,
            status=values.status,
            due_date=values.due_date,
            created_at=now,
            updated_at=now,
        )
        self.session.add(milestone)
        self.session.flush()
        return milestone

    def update(
        self,
        milestone: MilestoneDB,
        values: dict,
    ) -> MilestoneDB:
        for field, value in values.items():
            setattr(milestone, field, value)
        milestone.updated_at = datetime.now(UTC)
        self.session.flush()
        return milestone

    def delete(self, milestone: MilestoneDB) -> None:
        self.session.delete(milestone)
        self.session.flush()
