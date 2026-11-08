from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.db.models.goal_status_history import GoalStatusHistoryDB
from app.db.models.goal_validation_run import GoalValidationRunDB
from app.db.models.goal_version import GoalVersionDB
from app.db.models.goal_version_approval import GoalVersionApprovalDB
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.repositories.base import BaseRepository

_MATERIAL_GOAL_FIELDS = {
    "title",
    "description",
    "scope",
    "goal_level",
    "organization_id",
    "start_date",
    "end_date",
    "source",
    "source_document_id",
    "structured_fields",
}


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
    goal_level: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    status: GoalStatus = GoalStatus.DRAFT,
    sub_status: GoalSubStatus | None = None,
    source: str | None = None,
    source_document_id: str | None = None,
    organization_id: str | None = None,
    structured_fields: dict | None = None,
    created_by_user_id: str | None = None,
) -> GoalDB:
        now = datetime.now(UTC)

        goal = GoalDB(
            id=goal_id,
            user_id=user_id,
            title=title,
            description=description,
            scope=scope,
            goal_level=goal_level,
            start_date=start_date,
            end_date=end_date,
            status=status,
            sub_status=sub_status or _default_sub_status(status),
            source=source,
            source_document_id=source_document_id,
            organization_id=organization_id,
            structured_fields=structured_fields or {},
            created_at=now,
            updated_at=now,
        )

        self.session.add(goal)
        self.session.flush()
        self.add_version(goal, created_by_user_id)

        return goal

    def update(
        self,
        goal_id: str,
        values: dict,
        changed_by_user_id: str | None = None,
    ) -> GoalDB | None:
        goal = self.get_by_id(goal_id)
        if goal is None:
            return None
        creates_version = any(
            field in _MATERIAL_GOAL_FIELDS
            and getattr(goal, field) != value
            for field, value in values.items()
        )
        for field, value in values.items():
            setattr(goal, field, value)
        goal.updated_at = datetime.now(UTC)
        self.session.flush()
        if creates_version:
            self.add_version(goal, changed_by_user_id)
        return goal

    def add_version(
        self,
        goal: GoalDB,
        created_by_user_id: str | None,
        *,
        origin: str = "USER",
    ) -> GoalVersionDB:
        latest_version = (
            self.session.query(GoalVersionDB.version)
            .filter(GoalVersionDB.goal_id == goal.id)
            .order_by(GoalVersionDB.version.desc())
            .first()
        )
        version = GoalVersionDB(
            id=str(uuid4()),
            goal_id=goal.id,
            version=(latest_version[0] + 1) if latest_version else 1,
            origin=origin,
            content=self._version_content(goal),
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        self.session.add(version)
        self.session.flush()
        return version

    def get_latest_version(self, goal_id: str) -> GoalVersionDB | None:
        return (
            self.session.query(GoalVersionDB)
            .filter(GoalVersionDB.goal_id == goal_id)
            .order_by(GoalVersionDB.version.desc())
            .first()
        )

    def has_ready_validation_for_version(
        self,
        goal_id: str,
        goal_version_id: str,
    ) -> bool:
        latest_run = (
            self.session.query(GoalValidationRunDB.status)
            .filter(
                GoalValidationRunDB.goal_id == goal_id,
                GoalValidationRunDB.goal_version_id == goal_version_id,
            )
            .order_by(
                GoalValidationRunDB.created_at.desc(),
                GoalValidationRunDB.id.desc(),
            )
            .first()
        )
        return latest_run is not None and latest_run[0] == "READY"

    def has_approval_for_version(self, goal_version_id: str) -> bool:
        return (
            self.session.query(GoalVersionApprovalDB.id)
            .filter(GoalVersionApprovalDB.goal_version_id == goal_version_id)
            .first()
            is not None
        )

    def approve_version(
        self,
        *,
        goal_id: str,
        goal_version_id: str,
        actor_user_id: str | None,
    ) -> GoalVersionApprovalDB:
        approval = GoalVersionApprovalDB(
            id=str(uuid4()),
            goal_id=goal_id,
            goal_version_id=goal_version_id,
            actor_user_id=actor_user_id,
            created_at=datetime.now(UTC),
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    @staticmethod
    def _version_content(goal: GoalDB) -> dict:
        criterion_versions = []
        for criterion in goal.criteria:
            if criterion.is_retired or not criterion.versions:
                continue
            latest = max(criterion.versions, key=lambda version: version.version)
            criterion_versions.append(
                {
                    "criterion_id": criterion.id,
                    "version_id": latest.id,
                    "version": latest.version,
                    "approval_status": latest.approval_status.value,
                    "definition": latest.definition,
                }
            )
        return {
            "title": goal.title,
            "description": goal.description,
            "scope": goal.scope.value if goal.scope is not None else None,
            "goal_level": goal.goal_level,
            "start_date": goal.start_date.isoformat() if goal.start_date else None,
            "end_date": goal.end_date.isoformat() if goal.end_date else None,
            "source": goal.source,
            "source_document_id": goal.source_document_id,
            "structured_fields": goal.structured_fields or {},
            "criterion_versions": criterion_versions,
        }

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
