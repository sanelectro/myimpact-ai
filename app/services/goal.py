from uuid import uuid4
from datetime import UTC, datetime


from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.db.models.goal_status_history import GoalStatusHistoryDB
from app.db.models.user import UserDB
from app.models.goal import (
    DEFAULT_SUB_STATUS_BY_GOAL_STATUS,
    VALID_SUB_STATUSES_BY_GOAL_STATUS,
    GoalCreate,
    GoalScope,
    GoalStatus,
    GoalSubStatus,
)
from app.repositories.goal import GoalRepository
from app.services.base import BaseService


ALLOWED_GOAL_TRANSITIONS = {
    GoalStatus.DRAFT: {GoalStatus.APPROVED, GoalStatus.ARCHIVED},
    GoalStatus.APPROVED: {GoalStatus.ACTIVE, GoalStatus.ARCHIVED},
    GoalStatus.ACTIVE: {GoalStatus.COMPLETED, GoalStatus.ARCHIVED},
    GoalStatus.COMPLETED: {GoalStatus.ACTIVE, GoalStatus.ARCHIVED},
    GoalStatus.ARCHIVED: set(),
}


class GoalService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = GoalRepository(session)

    def create_goal(self, goal_data: GoalCreate) -> GoalDB:
        organization_id = None
        if goal_data.scope == GoalScope.ORGANIZATION:
            user = self.session.get(UserDB, goal_data.user_id)
            if user is None or not isinstance(user.organization_id, str):
                raise ValueError(
                    "Set your company in your profile before creating an organization goal."
                )
            organization_id = user.organization_id

        goal = self.repository.create(
            goal_id=str(uuid4()),
            user_id=goal_data.user_id,
            title=goal_data.title,
            description=goal_data.description,
            scope=goal_data.scope,
            start_date=goal_data.start_date,
            end_date=goal_data.end_date,
            status=goal_data.status,
            sub_status=goal_data.sub_status,
            source=goal_data.source,
            source_document_id=goal_data.source_document_id,
            **({"organization_id": organization_id} if organization_id else {}),
        )
        self.commit()
        return goal


    def transition_status(
        self,
        goal_id: str,
        target: GoalStatus,
        *,
        reason: str | None = None,
        changed_by_user_id: str | None = None,
    ) -> GoalDB:
        goal = self.repository.get_by_id(goal_id)
        if goal is None:
            raise ValueError("Goal not found")

        previous_status = goal.status
        if target not in ALLOWED_GOAL_TRANSITIONS[previous_status]:
            raise ValueError("Invalid goal status transition")

        normalized_reason = (reason or "").strip() or None
        if previous_status == GoalStatus.COMPLETED and target == GoalStatus.ACTIVE and not normalized_reason:
            raise ValueError("A reason is required to reopen a completed goal")

        updates = {
            "status": target,
            "sub_status": DEFAULT_SUB_STATUS_BY_GOAL_STATUS[target],
        }
        if target == GoalStatus.ARCHIVED:
            if not normalized_reason:
                raise ValueError("A reason is required to deactivate a goal")
            updates["deactivation_reason"] = normalized_reason

        updated = self.repository.update(goal_id, updates)
        if updated is None:
            raise ValueError("Goal not found")
        self._record_status_transition(
            goal_id,
            previous_status,
            target,
            normalized_reason,
            changed_by_user_id,
        )
        self.commit()
        return updated

    def _record_status_transition(
        self,
        goal_id: str,
        from_status: GoalStatus,
        to_status: GoalStatus,
        reason: str | None,
        changed_by_user_id: str | None,
    ) -> None:
        self.repository.add_status_history(
            GoalStatusHistoryDB(
                id=str(uuid4()),
                goal_id=goal_id,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                changed_by_user_id=changed_by_user_id,
                created_at=datetime.now(UTC),
            )
        )

    def get_status_history(self, goal_id: str) -> list[GoalStatusHistoryDB]:
        return self.repository.get_status_history(goal_id)

    def get_goal_by_id(self, goal_id: str) -> GoalDB | None:
        return self.repository.get_by_id(goal_id)

    def get_goals_by_user_id(self, user_id: str) -> list[GoalDB]:
        return self.repository.get_by_user_id(user_id)
    def update_goal(self, goal_id: str, values: dict) -> GoalDB:
        existing = self.repository.get_by_id(goal_id)
        if existing is None:
            raise ValueError("Goal not found")

        updates = dict(values)
        target_scope = updates.get("scope", existing.scope)
        if target_scope != existing.scope or (
            target_scope == GoalScope.ORGANIZATION and not existing.organization_id
        ):
            if target_scope == GoalScope.ORGANIZATION:
                user = self.session.get(UserDB, existing.user_id)
                if user is None or not isinstance(user.organization_id, str):
                    raise ValueError(
                        "Set your company in your profile before selecting organization scope."
                    )
                updates["organization_id"] = user.organization_id
            else:
                updates["organization_id"] = None
        target_status = updates.get("status", existing.status)
        previous_status = existing.status
        if target_status != existing.status:
            if target_status == GoalStatus.ARCHIVED:
                raise ValueError("Use the deactivate action and provide a reason")
            if target_status not in ALLOWED_GOAL_TRANSITIONS[existing.status]:
                raise ValueError("Invalid goal status transition")
            updates.setdefault("sub_status", DEFAULT_SUB_STATUS_BY_GOAL_STATUS[target_status])
            if previous_status == GoalStatus.COMPLETED and target_status == GoalStatus.ACTIVE:
                raise ValueError("Use the reopen action and provide a reason")

        target_sub_status = updates.get("sub_status", existing.sub_status)
        if target_sub_status is not None and target_sub_status not in VALID_SUB_STATUSES_BY_GOAL_STATUS[target_status]:
            raise ValueError("Invalid goal status/sub-status combination")

        start_date = updates.get("start_date", existing.start_date)
        end_date = updates.get("end_date", existing.end_date)
        if start_date and end_date and end_date < start_date:
            raise ValueError("Target date cannot be before start date")

        goal = self.repository.update(goal_id, updates)
        if goal is None:
            raise ValueError("Goal not found")
        if target_status != previous_status:
            self._record_status_transition(
                goal_id,
                previous_status,
                target_status,
                None,
                None,
            )
        self.commit()
        return goal

    def delete_goal(self, goal_id: str) -> None:
        goal = self.repository.get_by_id(goal_id)
        if goal is None:
            raise ValueError("Goal not found")
        if goal.status != GoalStatus.ARCHIVED:
            raise ValueError("Only archived goals can be deleted")
        if not self.repository.delete(goal_id):
            raise ValueError("Goal not found")
        self.commit()
