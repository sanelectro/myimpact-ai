from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.models.goal import GoalStatus


class GoalHierarchyNotFound(ValueError):
    pass


class GoalHierarchyConflict(ValueError):
    pass


@dataclass(frozen=True)
class GoalRelationshipSnapshot:
    id: str
    parent_goal_id: str | None
    relationship_revision: int


@dataclass(frozen=True)
class GoalDateConflict:
    parent_goal_id: str
    child_goal_id: str
    child_field: str
    child_date: date
    parent_field: str
    parent_date: date


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

    def preview_proposed_date_conflicts(
        self, goal_id: str, user_id: str, start_date: date | None, end_date: date | None
    ) -> list[GoalDateConflict]:
        """Check adjacent live dates under hierarchy and ordered Goal locks.

        The caller owns the transaction and must acquire no conflicting locks
        before this method. This preview alone does not authorize publication.
        """
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("Target date cannot be before start date")
        if self.session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("Hierarchy date checks require PostgreSQL")
        if self.session.execute(text("SHOW transaction_isolation")).scalar_one() != "read committed":
            raise RuntimeError("Hierarchy date checks require READ COMMITTED isolation")
        self.session.execute(text("SELECT pg_advisory_xact_lock(1296650324, 1)"))
        initial = self.require_goal(goal_id, user_id)
        parent_id = initial.parent_goal_id
        goals = list(self.session.scalars(
            select(GoalDB)
            .where(or_(
                GoalDB.id.in_([goal_id, parent_id] if parent_id is not None else [goal_id]),
                GoalDB.parent_goal_id == goal_id,
            ))
            .order_by(GoalDB.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ))
        by_id = {goal.id: goal for goal in goals}
        current = by_id.get(goal_id)
        if current is None or current.user_id != user_id:
            raise GoalHierarchyNotFound("Goal not found")
        if current.parent_goal_id != parent_id:
            raise GoalHierarchyConflict("The goal hierarchy changed")
        if any(goal.user_id != user_id for goal in goals):
            raise GoalHierarchyConflict("A related goal is not owned by the employee")

        conflicts: list[GoalDateConflict] = []
        if parent_id is not None:
            parent = by_id.get(parent_id)
            if parent is None:
                raise GoalHierarchyConflict("The parent goal is missing")
            conflicts.extend(_date_conflicts(
                parent.id, parent.start_date, parent.end_date, goal_id, start_date, end_date
            ))
        for child in goals:
            if child.parent_goal_id == goal_id and child.status in {
                GoalStatus.DRAFT, GoalStatus.APPROVED, GoalStatus.ACTIVE,
            }:
                conflicts.extend(_date_conflicts(
                    goal_id, start_date, end_date, child.id, child.start_date, child.end_date
                ))
        return conflicts

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


def _date_conflicts(
    parent_id: str,
    parent_start: date | None,
    parent_end: date | None,
    child_id: str,
    child_start: date | None,
    child_end: date | None,
) -> list[GoalDateConflict]:
    conflicts = []
    for child_field, child_date in (("start_date", child_start), ("end_date", child_end)):
        if child_date is None:
            continue
        for parent_field, parent_date, outside in (
            ("start_date", parent_start, parent_start is not None and child_date < parent_start),
            ("end_date", parent_end, parent_end is not None and child_date > parent_end),
        ):
            if outside and parent_date is not None:
                conflicts.append(GoalDateConflict(
                    parent_id, child_id, child_field, child_date, parent_field, parent_date
                ))
    return conflicts
