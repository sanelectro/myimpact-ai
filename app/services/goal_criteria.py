from importlib.resources import files
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models.goal import GoalDB
from app.db.models.goal_criterion import GoalCriterionAssessmentDB
from app.exceptions import GoalCriteriaGenerationError
from app.models.goal import Goal
from app.models.goal_criteria import (
    GoalAssessmentLifecycle,
    GoalCriteriaGenerationResult,
    GoalCriterionApprovalStatus,
    GoalCriterionCreateRequest,
    GoalCriterionDefinition,
    GoalCriterionResponse,
    GoalCriterionType,
    GoalCriterionUpdateRequest,
)
from app.models.llm import LLMRequest
from app.repositories.goal_criterion import GoalAssessmentRepository, GoalCriterionRepository
from app.services.base import BaseService
from app.services.llm.interface import ILLMService

CRITERIA_PROMPT_VERSION = "m66-criteria-v1"


def _normalize_json_response(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


def _criteria_prompt() -> str:
    return files("app.prompts").joinpath("m66_criteria_generation.md").read_text()


class GoalCriteriaService(BaseService):
    def __init__(self, session: Session, llm_service: ILLMService | None = None):
        super().__init__(session)
        self.repository = GoalCriterionRepository(session)
        self.assessment_repository = GoalAssessmentRepository(session)
        self.llm_service = llm_service

    def list_for_goal(self, goal_id: str) -> list:
        return self.repository.get_by_goal_id(goal_id)

    def create_manual(
        self,
        goal_id: str,
        user_id: str,
        request: GoalCriterionCreateRequest,
    ):
        criterion = self.repository.create_criterion(
            criterion_id=str(uuid4()),
            goal_id=goal_id,
            created_by_user_id=user_id,
        )
        self.repository.add_version(
            version_id=str(uuid4()),
            criterion=criterion,
            criterion_type=request.definition.criterion_type,
            definition=request.definition.model_dump(mode="json"),
            created_by_user_id=user_id,
        )
        self.commit()
        return self.repository.get_by_id(criterion.id)

    def add_version(
        self,
        goal_id: str,
        criterion_id: str,
        user_id: str,
        request: GoalCriterionUpdateRequest,
    ):
        criterion = self.repository.get_by_id_and_goal(criterion_id, goal_id)
        if criterion is None or criterion.is_retired:
            raise ValueError("Criterion not found")
        version = self.repository.add_version(
            version_id=str(uuid4()),
            criterion=criterion,
            criterion_type=request.definition.criterion_type,
            definition=request.definition.model_dump(mode="json"),
            created_by_user_id=user_id,
        )
        if criterion.current_version is not None:
            self._obsolete_assessments(criterion.id, "Criterion definition edited")
        self.commit()
        return self.repository.get_by_id(criterion.id), version

    def approve_version(
        self,
        goal_id: str,
        criterion_id: str,
        version_id: str,
        user_id: str,
    ):
        criterion = self.repository.get_by_id_and_goal(criterion_id, goal_id)
        if criterion is None or criterion.is_retired:
            raise ValueError("Criterion not found")
        version = next((item for item in criterion.versions if item.id == version_id), None)
        if version is None:
            raise ValueError("Criterion version not found")
        if version.approval_status != GoalCriterionApprovalStatus.PROPOSED:
            raise ValueError("Only proposed criterion versions can be approved")
        previous_version = criterion.current_version
        self.repository.approve_version(criterion, version, user_id)
        if previous_version is not None and previous_version != version.version:
            self._obsolete_assessments(criterion.id, "Criterion version approved")
        self.commit()
        return self.repository.get_by_id(criterion.id)

    def retire(self, goal_id: str, criterion_id: str) -> None:
        criterion = self.repository.get_by_id_and_goal(criterion_id, goal_id)
        if criterion is None:
            raise ValueError("Criterion not found")
        if criterion.is_retired:
            return
        self.repository.retire(criterion)
        self._obsolete_assessments(criterion.id, "Criterion retired")
        self.commit()

    async def generate(
        self,
        goal: GoalDB,
        user_id: str,
    ) -> list:
        if self.llm_service is None:
            raise GoalCriteriaGenerationError("Criteria generation is not configured.")
        prompt = (
            _criteria_prompt()
            + "\n\nGOAL\n"
            + f"title: {goal.title}\n"
            + f"description: {goal.description or ''}\n"
            + f"scope: {goal.scope.value}\n"
            + f"start_date: {goal.start_date.isoformat() if goal.start_date else ''}\n"
            + f"target_date: {goal.end_date.isoformat() if goal.end_date else ''}\n"
        )
        try:
            response = await self.llm_service.generate(
                LLMRequest(
                    prompt=prompt,
                    response_format={"type": "json_object"},
                )
            )
        except Exception as exc:
            raise GoalCriteriaGenerationError("Criteria generation provider failed.") from exc
        try:
            result = GoalCriteriaGenerationResult.model_validate_json(
                _normalize_json_response(response.content)
            )
        except ValidationError as exc:
            raise GoalCriteriaGenerationError(
                "Criteria generation returned an invalid response."
            ) from exc

        normalized = [item.description.strip().casefold() for item in result.criteria]
        if len(normalized) != len(set(normalized)):
            raise GoalCriteriaGenerationError(
                "Criteria generation returned duplicate criteria."
            )

        created_ids: list[str] = []
        try:
            for proposal in result.criteria:
                criterion = self.repository.create_criterion(
                    criterion_id=str(uuid4()),
                    goal_id=goal.id,
                    created_by_user_id=user_id,
                )
                definition = proposal.model_dump(mode="json")
                self.repository.add_version(
                    version_id=str(uuid4()),
                    criterion=criterion,
                    criterion_type=proposal.criterion_type,
                    definition=definition,
                    created_by_user_id=user_id,
                    prompt_version=CRITERIA_PROMPT_VERSION,
                    model_version=response.model,
                )
                created_ids.append(criterion.id)
            self.commit()
        except Exception:
            self.session.rollback()
            raise
        return [
            criterion
            for criterion_id in created_ids
            if (criterion := self.repository.get_by_id(criterion_id)) is not None
        ]

    def _obsolete_assessments(self, criterion_id: str, reason: str) -> None:
        assessments = (
            self.session.query(GoalCriterionAssessmentDB)
            .filter(
                GoalCriterionAssessmentDB.criterion_id == criterion_id,
                GoalCriterionAssessmentDB.lifecycle_state
                != GoalAssessmentLifecycle.OBSOLETE,
            )
            .all()
        )
        from datetime import UTC, datetime

        from app.db.models.goal_criterion import GoalCriterionAssessmentEventDB

        for assessment in assessments:
            assessment.lifecycle_state = GoalAssessmentLifecycle.OBSOLETE
            assessment.invalidation_reason = reason
            self.assessment_repository.add_event(
                GoalCriterionAssessmentEventDB(
                    id=str(uuid4()),
                    assessment_id=assessment.id,
                    event_type="LIFECYCLE_CHANGED",
                    lifecycle_state=GoalAssessmentLifecycle.OBSOLETE,
                    actor_user_id=None,
                    details={"reason": reason},
                    created_at=datetime.now(UTC),
                )
            )
