import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.db.models.goal_baseline_observation import GoalBaselineObservationDB
from app.db.models.goal_definition_proposal import (
    GoalCommandReceiptDB,
    GoalDefinitionProposalHeadDB,
)
from app.db.models.goal_version import GoalVersionDB
from app.models.goal import GoalStatus, GoalStructuredFields
from app.models.milestone import MilestoneUpdate
from app.repositories.goal import GoalRepository
from app.services.goal_baseline_observations import GoalBaselineObservationService

_COMMAND_KIND = "PREPARE_DEFINITION"
_PLAIN_TEXT = re.compile(r"[A-Za-z0-9 ]*\Z")


class GoalProposalConflict(ValueError):
    pass


class GoalMilestoneProposalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    milestone_id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    completion_criteria: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None

    @field_validator("milestone_id")
    @classmethod
    def require_milestone_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Milestone ID cannot be blank")
        return value

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str | None) -> str | None:
        return MilestoneUpdate.validate_title(value)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set - {"milestone_id"}:
            raise ValueError("At least one milestone definition field is required")
        return self


class GoalProposalChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    start_date: date | None = None
    end_date: date | None = None
    structured_fields: GoalStructuredFields | None = None
    milestone_updates: list[GoalMilestoneProposalUpdate] | None = Field(default=None, min_length=1)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("Title cannot be blank")
        return value

    @field_validator("structured_fields")
    @classmethod
    def require_structured_fields(cls, value: GoalStructuredFields | None) -> GoalStructuredFields:
        if value is None:
            raise ValueError("Structured fields cannot be null")
        return value

    @field_validator("milestone_updates")
    @classmethod
    def require_unique_milestone_updates(
        cls, value: list[GoalMilestoneProposalUpdate] | None
    ) -> list[GoalMilestoneProposalUpdate]:
        if value is None:
            raise ValueError("Milestone updates cannot be null")
        ids = [update.milestone_id for update in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Milestone updates must have unique IDs")
        return value

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("At least one proposal field is required")
        return self


@dataclass(frozen=True)
class GoalProposalResult:
    goal_id: str
    version_id: str
    revision: int
    outcome: str


def _equivalent_text(original: object, proposed: object) -> bool:
    if original == proposed:
        return True
    return (
        isinstance(original, str)
        and isinstance(proposed, str)
        and _PLAIN_TEXT.fullmatch(original) is not None
        and _PLAIN_TEXT.fullmatch(proposed) is not None
        and len(original) - len(original.lstrip(" ")) < 4
        and len(proposed) - len(proposed.lstrip(" ")) < 4
        and original.split() == proposed.split()
    )


def _equivalent_definition(original: object, proposed: object) -> bool:
    if type(original) is not type(proposed):
        return False
    if isinstance(original, str):
        return _equivalent_text(original, proposed)
    if isinstance(original, dict) and isinstance(proposed, dict):
        return original.keys() == proposed.keys() and all(
            _equivalent_definition(original[key], proposed[key]) for key in original
        )
    if isinstance(original, list) and isinstance(proposed, list):
        return len(original) == len(proposed) and all(
            _equivalent_definition(left, right) for left, right in zip(original, proposed)
        )
    return original == proposed


class GoalDefinitionProposalService:
    """Stage an internal proposal; the caller owns the transaction."""

    def __init__(self, session: Session):
        self.session = session
        self.goals = GoalRepository(session)

    def require_matching_baseline(
        self, goal: GoalDB, expected_base_version_id: str, expected_relationship_revision: int
    ) -> GoalVersionDB:
        """Check observed state; callers provide authorization and serialization."""
        if goal.status not in {GoalStatus.APPROVED, GoalStatus.ACTIVE}:
            raise GoalProposalConflict("Only approved or active goals can have a revised proposal")
        if goal.operative_goal_version_id != expected_base_version_id:
            raise GoalProposalConflict("The operative goal definition changed or is not selected")
        if goal.relationship_revision != expected_relationship_revision:
            raise GoalProposalConflict("The goal relationship changed")
        base = self.goals.get_operative_version(goal.id)
        latest_standard = self.goals.get_latest_version(goal.id)
        if base is None or latest_standard is None:
            raise GoalProposalConflict("The current baseline is not supported or has changed")
        if base.definition_kind == "STANDARD":
            matches_source = latest_standard.id == base.id
        elif base.definition_kind == "OBSERVED":
            observation = self.session.execute(
                select(GoalBaselineObservationDB)
                .where(GoalBaselineObservationDB.goal_id == goal.id)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            matches_source = (
                observation is not None
                and observation.goal_version_id == base.id
                and observation.source_standard_version_id == latest_standard.id
            )
        else:
            matches_source = False
        if not matches_source:
            raise GoalProposalConflict("The current baseline is not supported or has changed")
        self.session.expire(goal, ["criteria", "milestones"])
        for criterion in goal.criteria:
            self.session.expire(criterion, ["versions"])
        if self.goals.compare_live_definition(goal, base.content):
            raise GoalProposalConflict("The live goal no longer matches the selected baseline")
        return base

    def require_prepared_proposal(
        self, goal_id: str, proposal_version_id: str, actor_user_id: str
    ) -> GoalVersionDB:
        """Check current prepared state; callers provide any required serialization."""
        goal = self.session.execute(
            select(GoalDB).where(GoalDB.id == goal_id).execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if goal is None or goal.user_id != actor_user_id:
            raise ValueError("Goal proposal not found")
        head = self.session.execute(
            select(GoalDefinitionProposalHeadDB)
            .where(GoalDefinitionProposalHeadDB.goal_id == goal_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if head is None or head.proposal_version_id != proposal_version_id:
            raise GoalProposalConflict("Goal proposal not found or superseded")
        self.require_matching_baseline(goal, head.base_version_id, head.relationship_revision)
        version = self.session.get(GoalVersionDB, proposal_version_id)
        if (
            version is None
            or version.goal_id != goal_id
            or version.definition_kind != "PROPOSAL"
            or version.origin != "USER"
        ):
            raise GoalProposalConflict("Goal proposal not found or superseded")
        return version

    def stage_proposal(
        self,
        *,
        goal_id: str,
        actor_user_id: str,
        idempotency_key: str,
        expected_base_version_id: str,
        expected_proposal_revision: int,
        expected_relationship_revision: int,
        changes: GoalProposalChanges,
    ) -> GoalProposalResult:
        return self._stage_proposal(
            goal_id=goal_id,
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
            expected_base_version_id=expected_base_version_id,
            expected_proposal_revision=expected_proposal_revision,
            expected_relationship_revision=expected_relationship_revision,
            changes=changes,
            observation_source_version_id=None,
        )

    def stage_observed_proposal(
        self,
        *,
        goal_id: str,
        actor_user_id: str,
        idempotency_key: str,
        expected_source_version_id: str,
        expected_proposal_revision: int,
        expected_relationship_revision: int,
        changes: GoalProposalChanges,
    ) -> GoalProposalResult:
        """Stage both operations; the caller must commit or roll back the outer transaction.

        A nested transaction flushes pending session changes before its savepoint.
        Callers must also respect idempotency-before-Goal lock ordering.
        """
        if not expected_source_version_id:
            raise ValueError("An expected standard source version is required")
        if expected_proposal_revision < 0 or expected_relationship_revision < 0:
            raise ValueError("Expected revisions cannot be negative")
        with self.session.begin_nested():
            self._lock_prepare(actor_user_id, idempotency_key)
            goal = self.goals.get_by_id_for_update(goal_id)
            if goal is None or goal.user_id != actor_user_id:
                raise ValueError("Goal not found")
            receipt = self.session.get(
                GoalCommandReceiptDB, (actor_user_id, _COMMAND_KIND, idempotency_key)
            )
            if receipt is not None:
                if receipt.goal_id != goal_id:
                    raise GoalProposalConflict("Idempotency key was already used for a different request")
                observation = self.session.get(GoalBaselineObservationDB, goal_id)
                if observation is None:
                    raise GoalProposalConflict("Idempotency key was already used for a different request")
            else:
                observation = GoalBaselineObservationService(self.session).stage_observed_baseline(
                    goal_id=goal_id,
                    actor_user_id=actor_user_id,
                    expected_source_version_id=expected_source_version_id,
                    expected_relationship_revision=expected_relationship_revision,
                )
            return self._stage_proposal(
                goal_id=goal_id,
                actor_user_id=actor_user_id,
                idempotency_key=idempotency_key,
                expected_base_version_id=observation.goal_version_id,
                expected_proposal_revision=expected_proposal_revision,
                expected_relationship_revision=expected_relationship_revision,
                changes=changes,
                observation_source_version_id=expected_source_version_id,
            )

    def _lock_prepare(self, actor_user_id: str, idempotency_key: str) -> None:
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise ValueError("An idempotency key of at most 128 characters is required")
        if self.session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("Proposal preparation requires PostgreSQL")
        isolation = self.session.execute(text("SHOW transaction_isolation")).scalar_one()
        if isolation != "read committed":
            raise RuntimeError("Proposal preparation requires READ COMMITTED isolation")
        lock_input = json.dumps(
            [_COMMAND_KIND, actor_user_id, idempotency_key],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        lock_id = int.from_bytes(hashlib.sha256(lock_input).digest()[:8], "big", signed=True)
        self.session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

    def _stage_proposal(
        self,
        *,
        goal_id: str,
        actor_user_id: str,
        idempotency_key: str,
        expected_base_version_id: str,
        expected_proposal_revision: int,
        expected_relationship_revision: int,
        changes: GoalProposalChanges,
        observation_source_version_id: str | None,
    ) -> GoalProposalResult:
        if expected_proposal_revision < 0 or expected_relationship_revision < 0:
            raise ValueError("Expected revisions cannot be negative")
        payload = {
            "goal_id": goal_id,
            "expected_base_version_id": expected_base_version_id,
            "expected_proposal_revision": expected_proposal_revision,
            "expected_relationship_revision": expected_relationship_revision,
            "changes": changes.model_dump(mode="json", exclude_unset=True),
        }
        if observation_source_version_id is not None:
            payload["observation_source_version_id"] = observation_source_version_id
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        self._lock_prepare(actor_user_id, idempotency_key)
        goal = self.goals.get_by_id_for_update(goal_id)
        if goal is None or goal.user_id != actor_user_id:
            raise ValueError("Goal not found")
        receipt = self.session.get(
            GoalCommandReceiptDB, (actor_user_id, _COMMAND_KIND, idempotency_key)
        )
        if receipt is not None:
            if receipt.request_hash != request_hash:
                raise GoalProposalConflict("Idempotency key was already used for a different request")
            return GoalProposalResult(
                goal_id=receipt.goal_id,
                version_id=receipt.result_version_id,
                revision=receipt.result_revision,
                outcome=receipt.outcome,
            )

        base = self.require_matching_baseline(
            goal, expected_base_version_id, expected_relationship_revision
        )

        head = self.session.execute(
            select(GoalDefinitionProposalHeadDB)
            .where(GoalDefinitionProposalHeadDB.goal_id == goal_id)
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if (head.revision if head else 0) != expected_proposal_revision:
            raise GoalProposalConflict("The goal proposal changed")
        if head and (
            head.base_version_id != base.id
            or head.relationship_revision != expected_relationship_revision
        ):
            raise GoalProposalConflict("The goal proposal baseline changed")
        source = self.session.get(GoalVersionDB, head.proposal_version_id) if head else base
        if source is None or source.goal_id != goal_id or (
            head is not None
            and (source.definition_kind != "PROPOSAL" or source.origin != "USER")
        ):
            raise RuntimeError("Goal proposal head references a missing version")
        content = deepcopy(source.content)
        changed = False
        for field, value in payload["changes"].items():
            if field == "milestone_updates":
                definitions = {item["milestone_id"]: item for item in content["milestone_definitions"]}
                for update in value:
                    milestone = definitions.get(update["milestone_id"])
                    if milestone is None:
                        raise ValueError("Milestone not found in proposal definition")
                    for name, proposed in update.items():
                        if name != "milestone_id" and not _equivalent_definition(
                            milestone[name], proposed
                        ):
                            milestone[name] = proposed
                            changed = True
                continue
            if field == "structured_fields":
                merged = deepcopy(content[field])
                if "deferred_requirements" in value and not _equivalent_definition(
                    merged.get("deferred_requirements", []), value["deferred_requirements"]
                ):
                    raise ValueError("Proposal changes to deferred requirements are not supported yet")
                merged.update(value)
                previous = GoalStructuredFields.model_validate(content[field]).model_dump(mode="json")
                proposed = GoalStructuredFields.model_validate(merged).model_dump(mode="json")
                if _equivalent_definition(previous, proposed):
                    continue
                value = merged
            equivalent = (
                _equivalent_definition(content[field], value)
                if field in {"title", "description", "structured_fields"}
                else content[field] == value
            )
            if not equivalent:
                content[field] = value
                changed = True
        start = date.fromisoformat(content["start_date"]) if content["start_date"] else None
        end = date.fromisoformat(content["end_date"]) if content["end_date"] else None
        if start is not None and end is not None and end < start:
            raise ValueError("Target date cannot be before start date")

        if changed:
            latest_number = self.session.execute(
                select(func.max(GoalVersionDB.version)).where(GoalVersionDB.goal_id == goal_id)
            ).scalar_one()
            version = GoalVersionDB(
                id=str(uuid4()),
                goal_id=goal_id,
                version=(latest_number or 0) + 1,
                origin="USER",
                definition_kind="PROPOSAL",
                content=content,
                created_by_user_id=actor_user_id,
                created_at=datetime.now(UTC),
            )
            self.session.add(version)
            self.session.flush()
            if head is None:
                head = GoalDefinitionProposalHeadDB(
                    goal_id=goal_id,
                    base_version_id=base.id,
                    proposal_version_id=version.id,
                    revision=1,
                    relationship_revision=expected_relationship_revision,
                )
                self.session.add(head)
            else:
                head.proposal_version_id = version.id
                head.revision += 1
            result = GoalProposalResult(goal_id, version.id, head.revision, "CREATED")
        else:
            result = GoalProposalResult(
                goal_id, source.id, head.revision if head else 0, "NO_CHANGE"
            )

        self.session.add(
            GoalCommandReceiptDB(
                actor_user_id=actor_user_id,
                command_kind=_COMMAND_KIND,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                goal_id=goal_id,
                result_version_id=result.version_id,
                result_revision=result.revision,
                outcome=result.outcome,
                created_at=datetime.now(UTC),
            )
        )
        self.session.flush()
        return result
