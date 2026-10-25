from datetime import UTC, datetime

from sqlalchemy.orm import Session, selectinload

from app.db.models.goal_criterion import (
    GoalAssessmentRunDB,
    GoalCriterionAssessmentDB,
    GoalCriterionAssessmentEventDB,
    GoalCriterionAssessmentEvidenceDB,
    GoalCriterionDB,
    GoalCriterionVersionDB,
)
from app.models.goal_criteria import (
    GoalAssessmentRunStatus,
    GoalCriterionApprovalStatus,
)
from app.repositories.base import BaseRepository


class GoalCriterionRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, criterion_id: str) -> GoalCriterionDB | None:
        return (
            self.session.query(GoalCriterionDB)
            .options(selectinload(GoalCriterionDB.versions))
            .filter(GoalCriterionDB.id == criterion_id)
            .one_or_none()
        )

    def get_by_id_and_goal(
        self,
        criterion_id: str,
        goal_id: str,
    ) -> GoalCriterionDB | None:
        return (
            self.session.query(GoalCriterionDB)
            .options(selectinload(GoalCriterionDB.versions))
            .filter(
                GoalCriterionDB.id == criterion_id,
                GoalCriterionDB.goal_id == goal_id,
            )
            .one_or_none()
        )

    def get_by_goal_id(self, goal_id: str) -> list[GoalCriterionDB]:
        return (
            self.session.query(GoalCriterionDB)
            .options(selectinload(GoalCriterionDB.versions))
            .filter(GoalCriterionDB.goal_id == goal_id)
            .order_by(GoalCriterionDB.created_at, GoalCriterionDB.id)
            .all()
        )

    def create_criterion(
        self,
        *,
        criterion_id: str,
        goal_id: str,
        created_by_user_id: str,
    ) -> GoalCriterionDB:
        now = datetime.now(UTC)
        criterion = GoalCriterionDB(
            id=criterion_id,
            goal_id=goal_id,
            current_version=None,
            is_retired=False,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(criterion)
        self.session.flush()
        return criterion

    def add_version(
        self,
        *,
        version_id: str,
        criterion: GoalCriterionDB,
        criterion_type,
        definition: dict,
        created_by_user_id: str,
        prompt_version: str | None = None,
        model_version: str | None = None,
    ) -> GoalCriterionVersionDB:
        version_number = max((version.version for version in criterion.versions), default=0) + 1
        version = GoalCriterionVersionDB(
            id=version_id,
            criterion_id=criterion.id,
            version=version_number,
            criterion_type=criterion_type,
            definition=definition,
            approval_status=GoalCriterionApprovalStatus.PROPOSED,
            created_by_user_id=created_by_user_id,
            prompt_version=prompt_version,
            model_version=model_version,
            created_at=datetime.now(UTC),
        )
        self.session.add(version)
        self.session.flush()
        criterion.versions.append(version)
        criterion.updated_at = datetime.now(UTC)
        return version

    def approve_version(
        self,
        criterion: GoalCriterionDB,
        version: GoalCriterionVersionDB,
        approved_by_user_id: str,
    ) -> GoalCriterionVersionDB:
        version.approval_status = GoalCriterionApprovalStatus.APPROVED
        version.approved_by_user_id = approved_by_user_id
        version.approved_at = datetime.now(UTC)
        criterion.current_version = version.version
        criterion.updated_at = datetime.now(UTC)
        self.session.flush()
        return version

    def retire(self, criterion: GoalCriterionDB) -> None:
        criterion.is_retired = True
        criterion.updated_at = datetime.now(UTC)
        self.session.flush()


class GoalAssessmentRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def create_run(
        self,
        *,
        run_id: str,
        batch_id: str | None,
        goal_id: str,
        requested_by_user_id: str,
        trigger: str,
        status: GoalAssessmentRunStatus = GoalAssessmentRunStatus.RUNNING,
    ) -> GoalAssessmentRunDB:
        now = datetime.now(UTC)
        run = GoalAssessmentRunDB(
            id=run_id,
            batch_id=batch_id,
            goal_id=goal_id,
            requested_by_user_id=requested_by_user_id,
            status=status,
            trigger=trigger,
            created_at=now,
            started_at=now if status == GoalAssessmentRunStatus.RUNNING else None,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(
        self,
        run: GoalAssessmentRunDB,
        status: GoalAssessmentRunStatus,
        error_message: str | None = None,
    ) -> None:
        run.status = status
        run.error_message = error_message
        run.finished_at = datetime.now(UTC)
        self.session.flush()

    def create_assessment(self, assessment: GoalCriterionAssessmentDB) -> None:
        self.session.add(assessment)
        self.session.flush()

    def add_evidence(self, evidence: GoalCriterionAssessmentEvidenceDB) -> None:
        self.session.add(evidence)
        self.session.flush()

    def add_event(self, event: GoalCriterionAssessmentEventDB) -> None:
        self.session.add(event)
        self.session.flush()

    def get_assessment(self, assessment_id: str) -> GoalCriterionAssessmentDB | None:
        return (
            self.session.query(GoalCriterionAssessmentDB)
            .options(
                selectinload(GoalCriterionAssessmentDB.evidence)
                .selectinload(GoalCriterionAssessmentEvidenceDB.evidence_mapping),
                selectinload(GoalCriterionAssessmentDB.events),
                selectinload(GoalCriterionAssessmentDB.criterion_version),
            )
            .filter(GoalCriterionAssessmentDB.id == assessment_id)
            .one_or_none()
        )

    def get_assessments_by_goal_id(
        self,
        goal_id: str,
    ) -> list[GoalCriterionAssessmentDB]:
        return (
            self.session.query(GoalCriterionAssessmentDB)
            .join(GoalCriterionDB)
            .options(
                selectinload(GoalCriterionAssessmentDB.evidence)
                .selectinload(GoalCriterionAssessmentEvidenceDB.evidence_mapping),
                selectinload(GoalCriterionAssessmentDB.events),
                selectinload(GoalCriterionAssessmentDB.criterion_version),
                selectinload(GoalCriterionAssessmentDB.run),
            )
            .filter(GoalCriterionDB.goal_id == goal_id)
            .order_by(GoalCriterionAssessmentDB.created_at.desc())
            .all()
        )

    def get_run_by_id(self, run_id: str) -> GoalAssessmentRunDB | None:
        return self.session.get(GoalAssessmentRunDB, run_id)

    def get_latest_run_by_goal_id(self, goal_id: str) -> GoalAssessmentRunDB | None:
        return (
            self.session.query(GoalAssessmentRunDB)
            .filter(GoalAssessmentRunDB.goal_id == goal_id)
            .order_by(GoalAssessmentRunDB.created_at.desc())
            .first()
        )
