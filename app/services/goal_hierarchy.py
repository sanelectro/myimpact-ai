from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB


class GoalHierarchyNotFound(ValueError):
    pass


class GoalHierarchyConflict(ValueError):
    pass


@dataclass(frozen=True)
class GoalRelationshipSnapshot:
    id: str
    parent_goal_id: str | None
    relationship_revision: int


class GoalHierarchyService:
    def __init__(self, session: Session):
        self.session = session

    def require_goal(self, goal_id: str, user_id: str) -> GoalDB:
        goal = self.session.execute(
            select(GoalDB)
            .where(GoalDB.id == goal_id, GoalDB.user_id == user_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if goal is None:
            raise GoalHierarchyNotFound("Goal not found")
        return goal

    def set_parent(
        self,
        goal_id: str,
        user_id: str,
        parent_goal_id: str | None,
        expected_revision: int,
        reason: str | None,
    ) -> GoalRelationshipSnapshot:
        return self._set_parent(goal_id, user_id, parent_goal_id, expected_revision, reason, commit=True)

    def stage_initial_parent(
        self, goal_id: str, user_id: str, parent_goal_id: str
    ) -> GoalRelationshipSnapshot:
        return self._set_parent(goal_id, user_id, parent_goal_id, 0, None, commit=False)

    def _set_parent(
        self,
        goal_id: str,
        user_id: str,
        parent_goal_id: str | None,
        expected_revision: int,
        reason: str | None,
        *,
        commit: bool,
    ) -> GoalRelationshipSnapshot:
        try:
            self.session.execute(text("SELECT pg_advisory_xact_lock(1296650324, 1)"))
            goal = self.require_goal(goal_id, user_id)
            if goal.relationship_revision != expected_revision:
                raise GoalHierarchyConflict("Relationship revision is stale; reload the goal")
            if parent_goal_id == goal.parent_goal_id:
                snapshot = GoalRelationshipSnapshot(goal.id, goal.parent_goal_id, goal.relationship_revision)
                if commit:
                    self.session.commit()
                return snapshot
            if parent_goal_id is not None:
                self.require_goal(parent_goal_id, user_id)
                if parent_goal_id == goal_id or self.session.execute(
                    text("""
                        WITH RECURSIVE ancestors(id, parent_goal_id) AS (
                            SELECT id, parent_goal_id FROM goals WHERE id = :parent_id
                            UNION
                            SELECT goal.id, goal.parent_goal_id
                            FROM goals AS goal JOIN ancestors ON goal.id = ancestors.parent_goal_id
                        )
                        SELECT EXISTS (SELECT 1 FROM ancestors WHERE id = :goal_id)
                    """),
                    {"parent_id": parent_goal_id, "goal_id": goal_id},
                ).scalar_one():
                    raise GoalHierarchyConflict("Goal hierarchy cannot contain cycles")
            self.session.execute(
                text("SELECT set_config('myimpact.relationship_actor', :actor, true)"),
                {"actor": user_id},
            )
            self.session.execute(
                text("SELECT set_config('myimpact.relationship_reason', :reason, true)"),
                {"reason": reason or ""},
            )
            goal.parent_goal_id = parent_goal_id
            self.session.flush()
            self.session.refresh(goal, ["parent_goal_id", "relationship_revision"])
            snapshot = GoalRelationshipSnapshot(goal.id, goal.parent_goal_id, goal.relationship_revision)
            if commit:
                self.session.commit()
            return snapshot
        except DBAPIError as exc:
            self.session.rollback()
            if getattr(exc.orig, "sqlstate", None) in {"23503", "40001", "40P01"}:
                raise GoalHierarchyConflict(
                    "The hierarchy changed concurrently; reload and retry"
                ) from exc
            raise
        except (GoalHierarchyNotFound, GoalHierarchyConflict):
            self.session.rollback()
            raise

    def hierarchy(self, goal_id: str, user_id: str, limit: int) -> tuple[GoalDB, list[GoalDB], str | None]:
        self.session.execute(text("SELECT pg_advisory_xact_lock(1296650324, 1)"))
        goal = self.require_goal(goal_id, user_id)
        ancestors, next_ancestor_id = self.ancestors(goal, user_id, limit)
        return goal, ancestors, next_ancestor_id

    def ancestors(self, goal: GoalDB, user_id: str, limit: int) -> tuple[list[GoalDB], str | None]:
        ancestors = []
        seen = {goal.id}
        parent_id = goal.parent_goal_id
        while parent_id is not None and len(ancestors) < limit:
            if parent_id in seen:
                raise GoalHierarchyConflict("Stored goal hierarchy contains a cycle")
            seen.add(parent_id)
            parent = self.require_goal(parent_id, user_id)
            ancestors.append(parent)
            parent_id = parent.parent_goal_id
        return ancestors, parent_id

    def children(self, goal_id: str, user_id: str, limit: int, offset: int) -> list[GoalDB]:
        self.require_goal(goal_id, user_id)
        return list(self.session.scalars(
            select(GoalDB)
            .where(GoalDB.parent_goal_id == goal_id, GoalDB.user_id == user_id)
            .order_by(GoalDB.created_at, GoalDB.id)
            .limit(limit)
            .offset(offset)
        ))

    def history(self, goal_id: str, user_id: str, limit: int, offset: int) -> list[dict]:
        self.require_goal(goal_id, user_id)
        rows = self.session.execute(
            text("""
                SELECT id, goal_id, old_parent_goal_id, new_parent_goal_id,
                       actor_user_id, reason, relationship_revision, created_at
                FROM goal_relationship_events
                WHERE goal_id = :goal_id
                ORDER BY relationship_revision DESC
                LIMIT :limit OFFSET :offset
            """),
            {"goal_id": goal_id, "limit": limit, "offset": offset},
        ).mappings()
        return [dict(row) for row in rows]
