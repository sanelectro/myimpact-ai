import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models.goal_definition_proposal import (
    GoalCommandReceiptDB,
    GoalDefinitionProposalHeadDB,
)
from app.db.models.goal_version import GoalVersionDB
from app.models.goal import GoalStatus
from app.repositories.goal import GoalRepository

_COMMAND_KIND = "PREPARE_DEFINITION"
_PLAIN_TEXT = re.compile(r"[A-Za-z0-9 ]*\Z")


class GoalProposalConflict(ValueError):
    pass


class GoalProposalTextChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("Title cannot be blank")
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


class GoalDefinitionProposalService:
    """Stage an internal text-only proposal; the caller owns the transaction."""

    def __init__(self, session: Session):
        self.session = session
        self.goals = GoalRepository(session)

    def stage_text_proposal(
        self,
        *,
        goal_id: str,
        actor_user_id: str,
        idempotency_key: str,
        expected_base_version_id: str,
        expected_proposal_revision: int,
        expected_relationship_revision: int,
        changes: GoalProposalTextChanges,
    ) -> GoalProposalResult:
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise ValueError("An idempotency key of at most 128 characters is required")
        if expected_proposal_revision < 0 or expected_relationship_revision < 0:
            raise ValueError("Expected revisions cannot be negative")
        if self.session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("Proposal preparation requires PostgreSQL")
        isolation = self.session.execute(text("SHOW transaction_isolation")).scalar_one()
        if isolation != "read committed":
            raise RuntimeError("Proposal preparation requires READ COMMITTED isolation")

        payload = {
            "goal_id": goal_id,
            "expected_base_version_id": expected_base_version_id,
            "expected_proposal_revision": expected_proposal_revision,
            "expected_relationship_revision": expected_relationship_revision,
            "changes": changes.model_dump(mode="json", exclude_unset=True),
        }
        request_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        lock_input = json.dumps(
            [_COMMAND_KIND, actor_user_id, idempotency_key],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        lock_id = int.from_bytes(hashlib.sha256(lock_input).digest()[:8], "big", signed=True)
        self.session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})

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

        if goal.status not in {GoalStatus.APPROVED, GoalStatus.ACTIVE}:
            raise GoalProposalConflict("Only approved or active goals can have a revised proposal")
        if goal.operative_goal_version_id != expected_base_version_id:
            raise GoalProposalConflict("The operative goal definition changed or is not selected")
        if goal.relationship_revision != expected_relationship_revision:
            raise GoalProposalConflict("The goal relationship changed")
        base = self.goals.get_operative_version(goal_id)
        latest_standard = self.goals.get_latest_version(goal_id)
        if base is None or base.definition_kind != "STANDARD" or (
            latest_standard is None or latest_standard.id != base.id
        ):
            raise GoalProposalConflict("The current baseline is not supported or has changed")
        self.session.expire(goal, ["criteria", "milestones"])
        for criterion in goal.criteria:
            self.session.expire(criterion, ["versions"])
        if self.goals.compare_live_definition(goal, base.content):
            raise GoalProposalConflict("The live goal no longer matches the selected baseline")

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
            if not _equivalent_text(content[field], value):
                content[field] = value
                changed = True

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
