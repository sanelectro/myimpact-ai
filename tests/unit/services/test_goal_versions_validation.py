import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Column, String, Table, create_engine
from sqlalchemy.orm import Session

import app.db.models
from app.db.base import Base
from app.db.models.goal_validation_run import GoalValidationRunDB
from app.db.models.user import UserDB
from app.models.goal import GoalScope, GoalStatus
from app.models.goal_criteria import GoalCriterionDefinition, GoalCriterionType
from app.repositories.goal import GoalRepository
from app.services.goal_validation import GoalSemanticValidationError
from app.services.goal_validation_runs import GoalValidationRunService


class _StructuredLLM:
    async def generate(self, request):
        assert request.prompt
        from app.models.llm import LLMResponse

        return LLMResponse(
            content=json.dumps({"issues": []}),
            model="test-model",
            provider="test-provider",
        )


class _FailedLLM:
    async def generate(self, request):
        raise RuntimeError("provider unavailable")


@pytest.fixture(autouse=True)
def _team_reference():
    created = "teams" not in Base.metadata.tables
    if created:
        table = Table("teams", Base.metadata, Column("id", String(64), primary_key=True))
    try:
        yield
    finally:
        if created:
            Base.metadata.remove(table)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.now(UTC)
    session.add(
        UserDB(
            id="owner-1",
            name="Owner",
            email="owner@example.test",
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    return engine, session


def _create_goal(session):
    return GoalRepository(session).create(
        goal_id="goal-1",
        user_id="owner-1",
        title="Deliver onboarding refresh",
        description="Release the updated onboarding flow",
        scope=GoalScope.PERSONAL,
        status=GoalStatus.DRAFT,
        structured_fields={
            "goal_type": "delivery",
            "accountability": "Product engineering lead",
            "deliverables": ["Updated onboarding flow"],
            "success_criteria": [
                GoalCriterionDefinition(
                    criterion_type=GoalCriterionType.BINARY,
                    description="The onboarding refresh is released",
                    completion_conditions="The updated flow is available to all new users.",
                ).model_dump(mode="json")
            ],
        },
        created_by_user_id="owner-1",
    )


def test_material_goal_edit_appends_immutable_version_and_status_edit_does_not():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        repository = GoalRepository(session)

        assert goal.versions[0].version == 1
        assert goal.versions[0].origin == "USER"

        repository.update(goal.id, {"status": GoalStatus.APPROVED})
        assert len(goal.versions) == 1

        repository.update(
            goal.id,
            {"title": "Deliver the revised onboarding refresh"},
            changed_by_user_id="owner-1",
        )
        session.flush()

        versions = (
            session.query(app.db.models.GoalVersionDB)
            .filter_by(goal_id=goal.id)
            .order_by(app.db.models.GoalVersionDB.version)
            .all()
        )
        assert [version.version for version in versions] == [1, 2]
        assert versions[1].content["title"] == "Deliver the revised onboarding refresh"
        assert versions[0].content["title"] == "Deliver onboarding refresh"
        assert versions[1].created_by_user_id == "owner-1"
    finally:
        session.close()
        engine.dispose()


def test_validation_runs_reference_exact_versions_and_retain_history():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        service = GoalValidationRunService(session, _StructuredLLM())

        first = asyncio.run(service.validate_latest(goal.id, "owner-1"))
        GoalRepository(session).update(
            goal.id,
            {"title": "Deliver the revised onboarding refresh"},
            changed_by_user_id="owner-1",
        )
        second = asyncio.run(service.validate_latest(goal.id, "owner-1"))
        history = service.get_history(goal.id)

        assert first.goal_version_id != second.goal_version_id
        assert first.goal_version.version == 1
        assert second.goal_version.version == 2
        assert first.status == second.status == "READY"
        assert first.rule_set_version == "goal-rules-v1"
        assert first.prompt_version == "goal-semantic-validation-v2"
        assert first.model_provider == "test-provider"
        assert first.model_version == "test-model"
        assert first.actor_user_id == "owner-1"
        assert {run.id for run in history} == {first.id, second.id}
    finally:
        session.close()
        engine.dispose()


def test_semantic_failure_does_not_persist_a_validation_run():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        service = GoalValidationRunService(session, _FailedLLM())

        with pytest.raises(GoalSemanticValidationError):
            asyncio.run(service.validate_latest(goal.id, "owner-1"))

        assert service.get_history(goal.id) == []
    finally:
        session.close()
        engine.dispose()


def test_newer_non_ready_validation_supersedes_previous_ready_run():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        service = GoalValidationRunService(session, _StructuredLLM())
        ready = asyncio.run(service.validate_latest(goal.id, "owner-1"))
        repository = GoalRepository(session)
        assert repository.has_ready_validation_for_version(goal.id, ready.goal_version_id)

        session.add(
            GoalValidationRunDB(
                id="newer-run",
                goal_id=goal.id,
                goal_version_id=ready.goal_version_id,
                status="NEEDS_REVIEW",
                findings=[],
                rule_set_version=ready.rule_set_version,
                prompt_version=ready.prompt_version,
                actor_user_id="owner-1",
                created_at=ready.created_at + timedelta(seconds=1),
            )
        )
        session.flush()

        assert not repository.has_ready_validation_for_version(goal.id, ready.goal_version_id)
        assert len(service.get_history(goal.id)) == 2
    finally:
        session.close()
        engine.dispose()


def test_edit_during_validation_retains_old_result_but_requires_revalidation():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        original_version = GoalRepository(session).get_latest_version(goal.id)

        class _EditingLLM(_StructuredLLM):
            async def generate(self, request):
                GoalRepository(session).update(
                    goal.id,
                    {"title": "Deliver revised onboarding"},
                    changed_by_user_id="owner-1",
                )
                return await super().generate(request)

        service = GoalValidationRunService(session, _EditingLLM())
        with pytest.raises(ValueError, match="changed during validation"):
            asyncio.run(service.validate_latest(goal.id, "owner-1"))

        history = service.get_history(goal.id)
        assert len(history) == 1
        assert history[0].goal_version_id == original_version.id
        latest_version = GoalRepository(session).get_latest_version(goal.id)
        assert latest_version.version == 2
        assert not GoalRepository(session).has_ready_validation_for_version(
            goal.id, latest_version.id
        )
    finally:
        session.close()
        engine.dispose()


def test_validation_logs_metadata_without_goal_content(caplog):
    engine, session = _session()
    try:
        goal = _create_goal(session)
        service = GoalValidationRunService(session, _StructuredLLM())
        with caplog.at_level(logging.INFO, logger="app.services.goal_validation_runs"):
            run = asyncio.run(service.validate_latest(goal.id, "owner-1"))
        record = next(
            item for item in caplog.records if item.message == "goal_validation_completed"
        )
        assert record.validation_run_id == run.id
        assert record.goal_version_id == run.goal_version_id
        assert record.duration_ms >= 0
        assert record.prompt_version == "goal-semantic-validation-v2"
        assert "onboarding" not in str(record.__dict__)
    finally:
        session.close()
        engine.dispose()
