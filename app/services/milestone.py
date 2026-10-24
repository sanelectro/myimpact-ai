from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.milestone import MilestoneDB
from app.models.milestone import MilestoneCreate
from app.repositories.milestone import MilestoneRepository
from app.services.base import BaseService


class MilestoneService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = MilestoneRepository(session)

    def get_milestones_by_goal_id(
        self,
        goal_id: str,
        *,
        include_archived: bool = False,
    ) -> list[MilestoneDB]:
        return self.repository.get_by_goal_id(
            goal_id,
            include_archived=include_archived,
        )

    def get_milestone_by_id_and_goal(
        self,
        milestone_id: str,
        goal_id: str,
    ) -> MilestoneDB | None:
        return self.repository.get_by_id_and_goal(milestone_id, goal_id)

    def create_milestone(self, goal_id: str, values: MilestoneCreate) -> MilestoneDB:
        milestone = self.repository.create(
            milestone_id=str(uuid4()),
            goal_id=goal_id,
            values=values,
        )
        self.commit()
        return milestone

    def update_milestone(self, goal_id: str, milestone_id: str, values: dict) -> MilestoneDB:
        milestone = self.repository.get_by_id_and_goal(milestone_id, goal_id)
        if milestone is None or milestone.archived_at is not None:
            raise ValueError("Milestone not found")
        updated = self.repository.update(milestone, values)
        self.commit()
        return updated

    def archive_milestone(self, goal_id: str, milestone_id: str) -> MilestoneDB:
        milestone = self.repository.get_by_id_and_goal(milestone_id, goal_id)
        if milestone is None:
            raise ValueError("Milestone not found")
        if milestone.archived_at is not None:
            raise ValueError("Milestone is already archived")
        updated = self.repository.update(
            milestone,
            {"archived_at": datetime.now(UTC)},
        )
        self.commit()
        return updated

    def delete_archived_milestone(self, goal_id: str, milestone_id: str) -> None:
        milestone = self.repository.get_by_id_and_goal(milestone_id, goal_id)
        if milestone is None:
            raise ValueError("Milestone not found")
        if milestone.archived_at is None:
            raise ValueError("Only archived milestones can be deleted")
        self.repository.delete(milestone)
        self.commit()
