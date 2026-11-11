from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.services.goal_definition_proposals import GoalDefinitionProposalService
from app.services.goal_hierarchy import GoalDateConflict, GoalHierarchyService


@dataclass(frozen=True)
class GoalProposalDatePreview:
    goal_id: str
    proposal_version_id: str
    conflicts: tuple[GoalDateConflict, ...]


class GoalProposalPreviewService:
    def __init__(self, session: Session):
        self.proposals = GoalDefinitionProposalService(session)
        self.hierarchy = GoalHierarchyService(session)

    def preview_dates(
        self, goal_id: str, proposal_version_id: str, actor_user_id: str
    ) -> GoalProposalDatePreview:
        """Preview an exact prepared proposal; the caller owns the transaction.

        Hierarchy and adjacent Goal locks remain held until the transaction ends.
        Commands needing an idempotency lock must acquire the hierarchy lock,
        then that lock, before calling; never acquire it after the Goal locks.
        """
        version = self.proposals.require_prepared_proposal(
            goal_id, proposal_version_id, actor_user_id
        )
        start = date.fromisoformat(version.content["start_date"]) if version.content["start_date"] else None
        end = date.fromisoformat(version.content["end_date"]) if version.content["end_date"] else None
        conflicts = self.hierarchy.preview_proposed_date_conflicts(goal_id, actor_user_id, start, end)
        self.proposals.require_prepared_proposal(goal_id, proposal_version_id, actor_user_id)
        return GoalProposalDatePreview(goal_id, proposal_version_id, tuple(conflicts))
