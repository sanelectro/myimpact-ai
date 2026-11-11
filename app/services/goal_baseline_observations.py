from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.db.models.goal_baseline_observation import GoalBaselineObservationDB
from app.db.models.goal_definition_proposal import GoalDefinitionProposalHeadDB
from app.db.models.goal_version import GoalVersionDB
from app.models.goal import GoalStatus
from app.repositories.goal import GoalRepository


class GoalBaselineConflict(ValueError):
    pass


class GoalBaselineObservationService:
    """Stage an observation after any required proposal idempotency lock."""

    def __init__(self, session: Session):
        self.session = session
        self.goals = GoalRepository(session)

    def stage_matching_baseline(
        self,
        *,
        goal_id: str,
        actor_user_id: str,
        expected_version_id: str,
        expected_relationship_revision: int,
    ) -> GoalBaselineObservationDB:
        goal, observation = self._observation_context(
            goal_id, actor_user_id, expected_relationship_revision
        )
        if observation is not None:
            if (
                observation.goal_version_id != expected_version_id
                or goal.operative_goal_version_id != expected_version_id
                or observation.source_standard_version_id not in {None, expected_version_id}
            ):
                raise GoalBaselineConflict("The observed baseline changed")
            self._require_matching_snapshot(goal, expected_version_id)
            return observation
        self._require_unselected(goal)
        self._require_matching_snapshot(goal, expected_version_id)

        observation = GoalBaselineObservationDB(
            goal_id=goal_id,
            goal_version_id=expected_version_id,
            observed_by_user_id=actor_user_id,
            observed_at=datetime.now(UTC),
            historical_effectivity="UNKNOWN",
        )
        self.session.add(observation)
        goal.operative_goal_version_id = expected_version_id
        self.session.flush()
        return observation

    def stage_observed_baseline(
        self,
        *,
        goal_id: str,
        actor_user_id: str,
        expected_source_version_id: str,
        expected_relationship_revision: int,
    ) -> GoalBaselineObservationDB:
        goal, observation = self._observation_context(
            goal_id, actor_user_id, expected_relationship_revision
        )
        if observation is not None:
            if (
                observation.source_standard_version_id != expected_source_version_id
                or goal.operative_goal_version_id != observation.goal_version_id
            ):
                raise GoalBaselineConflict("The observed baseline changed")
            self._require_source_version(goal_id, expected_source_version_id)
            version = self.session.get(GoalVersionDB, observation.goal_version_id)
            if version is None or version.goal_id != goal_id or version.definition_kind != "OBSERVED":
                raise GoalBaselineConflict("The observed baseline is invalid")
            self._refresh_definition(goal)
            if self.goals.compare_live_definition(goal, version.content):
                raise GoalBaselineConflict("The observed baseline does not match the live goal")
            return observation
        self._require_unselected(goal)
        self._require_source_version(goal_id, expected_source_version_id)
        version = self.goals.add_observed_baseline_version(goal, actor_user_id)
        observation = GoalBaselineObservationDB(
            goal_id=goal_id,
            goal_version_id=version.id,
            source_standard_version_id=expected_source_version_id,
            observed_by_user_id=actor_user_id,
            observed_at=datetime.now(UTC),
            historical_effectivity="UNKNOWN",
        )
        self.session.add(observation)
        goal.operative_goal_version_id = version.id
        self.session.flush()
        return observation

    def _observation_context(
        self, goal_id: str, actor_user_id: str, expected_relationship_revision: int
    ) -> tuple[GoalDB, GoalBaselineObservationDB | None]:
        if expected_relationship_revision < 0:
            raise ValueError("Expected relationship revision cannot be negative")
        if self.session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("Baseline observation requires PostgreSQL")
        isolation = self.session.execute(text("SHOW transaction_isolation")).scalar_one()
        if isolation != "read committed":
            raise RuntimeError("Baseline observation requires READ COMMITTED isolation")

        goal = self.goals.get_by_id_for_update(goal_id)
        if goal is None or goal.user_id != actor_user_id:
            raise ValueError("Goal not found")
        observation = self.session.execute(
            select(GoalBaselineObservationDB)
            .where(GoalBaselineObservationDB.goal_id == goal_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if goal.status not in {GoalStatus.APPROVED, GoalStatus.ACTIVE}:
            raise GoalBaselineConflict("Only approved or active goals can have a baseline observed")
        if goal.relationship_revision != expected_relationship_revision:
            raise GoalBaselineConflict("The goal relationship changed")
        return goal, observation

    def _require_unselected(self, goal: GoalDB) -> None:
        if goal.operative_goal_version_id is not None:
            raise GoalBaselineConflict("An operative baseline is already selected")
        head = self.session.get(GoalDefinitionProposalHeadDB, goal.id)
        if head is not None:
            raise GoalBaselineConflict("A proposal already exists for this goal")

    def _require_source_version(self, goal_id: str, expected_version_id: str) -> GoalVersionDB:
        version = self.goals.get_latest_version(goal_id)
        if version is None or version.id != expected_version_id:
            raise GoalBaselineConflict("The latest standard goal version changed")
        return version

    def _require_matching_snapshot(self, goal: GoalDB, expected_version_id: str) -> None:
        version = self._require_source_version(goal.id, expected_version_id)
        self._refresh_definition(goal)
        if self.goals.compare_live_definition(goal, version.content):
            raise GoalBaselineConflict("The latest snapshot does not match the live goal")

    def _refresh_definition(self, goal: GoalDB) -> None:
        self.session.expire(goal, ["criteria", "milestones"])
        for criterion in goal.criteria:
            self.session.expire(criterion, ["versions"])
