import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.db.models
from app.db.base import Base
from app.db.models.team import TeamDB as _TeamDB
from app.db.models.user import UserDB
from app.models.goal import GoalScope, GoalStatus
from app.repositories.goal import GoalRepository
from app.services.goal import GoalService
from app.services.goal_validation_runs import GoalValidationRunService


class _ReadyLLM:
    async def generate(self, request):
        from app.models.llm import LLMResponse

        return LLMResponse(
            content=json.dumps({"issues": []}),
            model="test-model",
            provider="test-provider",
        )


def _session():
    _ = _TeamDB
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
    goal = GoalRepository(session).create(
        goal_id="goal-1",
        user_id="owner-1",
        title="Deliver onboarding refresh",
        description="Release the updated onboarding flow",
        scope=GoalScope.PERSONAL,
        status=GoalStatus.DRAFT,
        structured_fields={
            "accountability": "Product engineering lead",
            "success_criteria": [
                {
                    "criterion_type": "BINARY",
                    "description": "The onboarding refresh is released",
                    "completion_conditions": (
                        "The updated flow is available to all new users."
                    ),
                }
            ],
        },
        created_by_user_id="owner-1",
    )
    session.commit()
    return engine, session, goal


def _validate(session, goal_id="goal-1"):
    return asyncio.run(
        GoalValidationRunService(session, _ReadyLLM()).validate_latest(
            goal_id, "owner-1"
        )
    )


def test_unvalidated_goal_cannot_be_approved_or_activated():
    engine, session, goal = _session()
    try:
        service = GoalService(session)
        with pytest.raises(ValueError, match="persisted READY validation run"):
            service.transition_status(
                goal.id, GoalStatus.APPROVED, changed_by_user_id="owner-1"
            )

        goal.status = GoalStatus.APPROVED
        session.flush()
        with pytest.raises(ValueError, match="persisted READY validation run"):
            service.transition_status(
                goal.id, GoalStatus.ACTIVE, changed_by_user_id="owner-1"
            )

        assert not service.repository.has_approval_for_version(
            service.repository.get_latest_version(goal.id).id
        )
    finally:
        session.close()
        engine.dispose()


def test_ready_latest_version_can_be_approved_and_activated():
    engine, session, goal = _session()
    try:
        run = _validate(session, goal.id)
        service = GoalService(session)

        approved = service.transition_status(
            goal.id, GoalStatus.APPROVED, changed_by_user_id="owner-1"
        )
        assert approved.status == GoalStatus.APPROVED
        active = service.transition_status(
            goal.id, GoalStatus.ACTIVE, changed_by_user_id="owner-1"
        )

        assert run.status == "READY"
        assert active.status == GoalStatus.ACTIVE
        approval = session.query(app.db.models.GoalVersionApprovalDB).one()
        assert approval.goal_version_id == run.goal_version_id
        assert approval.actor_user_id == "owner-1"
    finally:
        session.close()
        engine.dispose()


def test_revised_active_goal_requires_ready_and_reapproval_for_evidence():
    engine, session, goal = _session()
    try:
        service = GoalService(session)
        first_run = _validate(session, goal.id)
        service.transition_status(
            goal.id, GoalStatus.APPROVED, changed_by_user_id="owner-1"
        )
        service.transition_status(
            goal.id, GoalStatus.ACTIVE, changed_by_user_id="owner-1"
        )
        assert service.is_evidence_submission_eligible(goal)

        service.update_goal(
            goal.id,
            {"title": "Deliver the revised onboarding refresh"},
            changed_by_user_id="owner-1",
        )
        latest = service.repository.get_latest_version(goal.id)
        assert latest.id != first_run.goal_version_id
        assert not service.is_evidence_submission_eligible(goal)
        with pytest.raises(ValueError, match="persisted READY validation run"):
            service.transition_status(
                goal.id, GoalStatus.APPROVED, changed_by_user_id="owner-1"
            )

        second_run = _validate(session, goal.id)
        assert second_run.goal_version_id == latest.id
        assert not service.is_evidence_submission_eligible(goal)
        reapproved = service.transition_status(
            goal.id, GoalStatus.APPROVED, changed_by_user_id="owner-1"
        )

        assert reapproved.status == GoalStatus.ACTIVE
        assert service.is_evidence_submission_eligible(goal)
        approvals = session.query(app.db.models.GoalVersionApprovalDB).all()
        assert {approval.goal_version_id for approval in approvals} == {
            first_run.goal_version_id,
            second_run.goal_version_id,
        }
    finally:
        session.close()
        engine.dispose()


def test_legacy_goal_lifecycle_is_compatible_but_legacy_is_never_ready(
    monkeypatch,
):
    engine, session, goal = _session()
    try:
        monkeypatch.setattr(
            "app.services.goal.get_settings",
            lambda: SimpleNamespace(require_validation_for_legacy_goal_evidence=False),
        )
        version = GoalRepository(session).get_latest_version(goal.id)
        version.origin = "LEGACY"
        session.flush()

        service = GoalService(session)
        approved = service.transition_status(
            goal.id, GoalStatus.APPROVED, changed_by_user_id="owner-1"
        )
        assert approved.status == GoalStatus.APPROVED
        active = service.transition_status(
            goal.id, GoalStatus.ACTIVE, changed_by_user_id="owner-1"
        )
        assert active.status == GoalStatus.ACTIVE
        assert service.is_evidence_submission_eligible(goal)

        monkeypatch.setattr(
            "app.services.goal.get_settings",
            lambda: SimpleNamespace(require_validation_for_legacy_goal_evidence=True),
        )
        assert not service.is_evidence_submission_eligible(goal)
        with pytest.raises(ValueError, match="persisted READY validation run"):
            service.transition_status(
                goal.id, GoalStatus.ACTIVE, changed_by_user_id="owner-1"
            )

        with pytest.raises(
            ValueError, match="Legacy goal versions cannot be validated"
        ):
            _validate(session, goal.id)
        assert session.query(app.db.models.GoalValidationRunDB).count() == 0
    finally:
        session.close()
        engine.dispose()
