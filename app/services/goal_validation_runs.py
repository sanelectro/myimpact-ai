import logging
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.goal_validation_run import GoalValidationRunDB
from app.models.goal_validation import GoalValidationInput, GoalValidationTimeframe
from app.repositories.goal import GoalRepository
from app.repositories.goal_validation import GoalValidationRepository
from app.services.base import BaseService
from app.services.goal_validation import (
    GOAL_RULE_SET_VERSION,
    GOAL_SEMANTIC_VALIDATION_PROMPT_VERSION,
    GoalSemanticValidationError,
    GoalSemanticValidationService,
)
from app.services.llm.interface import ILLMService

logger = logging.getLogger(__name__)


class GoalValidationRunService(BaseService):
    def __init__(
        self,
        session: Session,
        llm_service: ILLMService | None = None,
    ):
        super().__init__(session)
        self.goal_repository = GoalRepository(session)
        self.repository = GoalValidationRepository(session)
        self.validator = GoalSemanticValidationService(llm_service)

    async def validate_latest(
        self,
        goal_id: str,
        actor_user_id: str,
    ) -> GoalValidationRunDB:
        started_at = perf_counter()
        version = self.goal_repository.get_latest_version(goal_id)
        if version is None:
            raise ValueError("Goal version not found")
        if version.origin == "LEGACY":
            raise ValueError(
                "Legacy goal versions cannot be validated; edit the goal to create a user-managed version"
            )

        content = version.content
        structured_fields = dict(content.get("structured_fields") or {})
        criterion_versions = content.get("criterion_versions") or []
        if criterion_versions:
            success_criteria = list(structured_fields.get("success_criteria") or [])
            for item in criterion_versions:
                definition = item["definition"]
                if definition not in success_criteria:
                    success_criteria.append(definition)
            structured_fields["success_criteria"] = success_criteria
        validation_input = GoalValidationInput(
            title=content.get("title"),
            description=content.get("description"),
            scope=content.get("scope"),
            timeframe=GoalValidationTimeframe(
                start_date=content.get("start_date"),
                end_date=content.get("end_date"),
            ),
            source=content.get("source"),
            source_document_id=content.get("source_document_id"),
            **structured_fields,
        )
        try:
            result, model_version, model_provider = await self.validator.validate_with_metadata(
                validation_input
            )
        except GoalSemanticValidationError:
            logger.warning(
                "goal_validation_failed",
                extra={
                    "goal_id": goal_id,
                    "goal_version_id": version.id,
                    "prompt_version": GOAL_SEMANTIC_VALIDATION_PROMPT_VERSION,
                    "duration_ms": round((perf_counter() - started_at) * 1000),
                },
            )
            raise

        run = GoalValidationRunDB(
            id=str(uuid4()),
            goal_id=goal_id,
            goal_version_id=version.id,
            status=result.status.value,
            findings=[
                finding.model_dump(mode="json") for finding in result.findings
            ],
            rule_set_version=GOAL_RULE_SET_VERSION,
            prompt_version=GOAL_SEMANTIC_VALIDATION_PROMPT_VERSION,
            model_provider=model_provider,
            model_version=model_version,
            actor_user_id=actor_user_id,
            created_at=datetime.now(UTC),
        )
        try:
            self.repository.create(run)
            self.commit()
        except Exception:
            self.rollback()
            logger.error(
                "goal_validation_persistence_failed",
                extra={"goal_id": goal_id, "goal_version_id": version.id},
            )
            raise
        logger.info(
            "goal_validation_completed",
            extra={
                "goal_id": goal_id,
                "goal_version_id": run.goal_version_id,
                "validation_run_id": run.id,
                "validation_status": run.status,
                "finding_dimensions": [finding.dimension.value for finding in result.findings],
                "model_provider": model_provider,
                "model_version": model_version,
                "prompt_version": GOAL_SEMANTIC_VALIDATION_PROMPT_VERSION,
                "rule_set_version": GOAL_RULE_SET_VERSION,
                "duration_ms": round((perf_counter() - started_at) * 1000),
            },
        )
        latest_version = self.goal_repository.get_latest_version(goal_id)
        if latest_version is None or latest_version.id != run.goal_version_id:
            logger.warning(
                "goal_validation_superseded",
                extra={"goal_id": goal_id, "goal_version_id": run.goal_version_id},
            )
            raise ValueError(
                "The goal changed during validation; the result was retained for "
                "the evaluated version. Revalidate the latest goal version."
            )
        return run

    def get_history(self, goal_id: str) -> list[GoalValidationRunDB]:
        return self.repository.list_for_goal(goal_id)
