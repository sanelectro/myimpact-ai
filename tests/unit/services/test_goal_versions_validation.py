import asyncio
import json
import logging
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Column, String, Table, create_engine
from sqlalchemy.orm import Session

import app.db.models
from app.db.base import Base
from app.db.models.goal_validation_run import GoalValidationRunDB
from app.db.models.milestone import MilestoneDB
from app.db.models.organization import OrganizationDB
from app.db.models.user import UserDB
from app.models.goal import GoalScope, GoalStatus
from app.models.api_v1_goals import GoalUpdateRequest
from app.models.goal_criteria import (
    GoalCriterionApprovalStatus,
    GoalCriterionDefinition,
    GoalCriterionType,
)
from app.models.milestone import MilestoneSource, MilestoneStatus
from app.repositories.goal import GoalRepository
from app.services.goal_validation import GoalSemanticValidationError
from app.services.goal_validation_runs import GoalValidationRunService
from app.services.goal import GoalService


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


def _add_proposal(session, goal, version_number, title):
    current = GoalRepository(session).get_latest_version(goal.id)
    content = deepcopy(current.content)
    content["title"] = title
    proposal = app.db.models.GoalVersionDB(
        id=f"proposal-{version_number}",
        goal_id=goal.id,
        version=version_number,
        origin="USER",
        definition_kind="PROPOSAL",
        content=content,
        created_by_user_id="owner-1",
        created_at=datetime.now(UTC),
    )
    session.add(proposal)
    session.flush()
    return proposal


@pytest.mark.parametrize("level", ["ANNUAL", "QUARTERLY", "MONTHLY", "SPRINT", None])
def test_goal_level_is_optional_and_versioned(level):
    engine, session = _session()
    try:
        goal = _create_goal(session)
        repository = GoalRepository(session)
        assert goal.goal_level is None
        assert goal.versions[0].content["goal_level"] is None

        updated = repository.update(goal.id, {"goal_level": level}, changed_by_user_id="owner-1")
        session.expire_all()
        assert updated.goal_level == level
        versions = session.query(app.db.models.GoalVersionDB).filter_by(goal_id=goal.id).order_by(
            app.db.models.GoalVersionDB.version
        ).all()
        assert len(versions) == (1 if level is None else 2)
        assert versions[-1].content["goal_level"] == level
    finally:
        session.close()
        engine.dispose()


def test_goal_level_request_rejects_unknown_value():
    from pydantic import ValidationError

    from app.models.api_v1_goals import GoalCreateRequest

    with pytest.raises(ValidationError):
        GoalCreateRequest(title="Goal", goal_level="WEEKLY")


def test_new_versions_do_not_implicitly_select_an_operative_version():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        repository = GoalRepository(session)
        first_version = repository.get_latest_version(goal.id)
        assert goal.operative_goal_version_id is None

        goal.operative_goal_version_id = first_version.id
        repository.update(goal.id, {"title": "Revised title"}, changed_by_user_id="owner-1")
        session.expire_all()
        assert goal.operative_goal_version_id == first_version.id
        assert repository.get_latest_version(goal.id).id != first_version.id
    finally:
        session.close()
        engine.dispose()


def test_old_structured_fields_writer_preserves_deferrals_and_versions_them():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        service = GoalService(session)
        initial = dict(goal.structured_fields)
        initial["deferred_requirements"] = [{
            "requirement": "target",
            "reason": "Await measurement",
            "due_date": "2026-12-01",
            "state": "OPEN",
        }]
        service.update_goal(goal.id, {"structured_fields": initial}, changed_by_user_id="owner-1")

        old_fields = dict(initial)
        old_fields.pop("deferred_requirements")
        old_fields["outcome"] = "Improved onboarding"
        request = GoalUpdateRequest(structured_fields=old_fields)
        service.update_goal(
            goal.id,
            {"structured_fields": request.structured_fields.model_dump(mode="json", exclude_unset=True)},
            changed_by_user_id="owner-1",
        )
        session.expire_all()
        updated = session.get(app.db.models.GoalDB, goal.id)
        assert updated.structured_fields["deferred_requirements"] == initial["deferred_requirements"]
        assert updated.structured_fields["outcome"] == "Improved onboarding"
        assert GoalRepository(session).get_latest_version(goal.id).content["structured_fields"]["deferred_requirements"] == initial["deferred_requirements"]
    finally:
        session.close()
        engine.dispose()


def test_validation_snapshots_deferrals_and_requirement_context():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        fields = dict(goal.structured_fields)
        fields["deferred_requirements"] = [{
            "requirement": "target", "reason": "Await decision", "resolution_stage": "Planning"
        }]
        GoalService(session).update_goal(goal.id, {"structured_fields": fields}, changed_by_user_id="owner-1")
        service = GoalValidationRunService(session, _StructuredLLM())
        run = asyncio.run(service.validate_latest(goal.id, "owner-1"))
        assert run.status == "READY"
        assert run.input_context["deferred_requirements"][0]["reason"] == "Await decision"
        assert next(item for item in run.result_context["requirements"] if item["requirement"] == "target")["state"] == "DEFERRED"
        assert service.get_requirements(goal.id)["goal_version"] == run.goal_version.version
    finally:
        session.close()
        engine.dispose()


def test_related_deferral_goal_must_be_owned_child_and_survives_disconnect():
    engine, session = _session()
    try:
        parent = _create_goal(session)
        repository = GoalRepository(session)
        child = repository.create(goal_id="child-1", user_id="owner-1", title="Child")
        service = GoalService(session)
        fields = dict(parent.structured_fields)
        fields["deferred_requirements"] = [{
            "requirement": "target",
            "reason": "Child will investigate",
            "resolution_stage": "Planning",
            "related_child_goal_id": child.id,
        }]
        with pytest.raises(ValueError, match="owned child"):
            service.update_goal(parent.id, {"structured_fields": fields}, changed_by_user_id="owner-1")
        child.parent_goal_id = parent.id
        session.flush()
        service.update_goal(parent.id, {"structured_fields": fields}, changed_by_user_id="owner-1")
        child.parent_goal_id = None
        session.flush()
        old_fields = dict(fields)
        old_fields.pop("deferred_requirements")
        service.update_goal(parent.id, {"structured_fields": old_fields}, changed_by_user_id="owner-1")
        assert parent.structured_fields["deferred_requirements"][0]["related_child_goal_id"] == child.id
    finally:
        session.close()
        engine.dispose()


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


def test_snapshot_refreshes_loaded_criteria_and_copies_nested_definitions():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        assert goal.criteria == []
        now = datetime.now(UTC)
        criterion = app.db.models.GoalCriterionDB(
            id="criterion-1",
            goal_id=goal.id,
            created_by_user_id="owner-1",
            created_at=now,
            updated_at=now,
        )
        session.add(criterion)
        session.flush()
        assert criterion.versions == []
        definition = {
            "criterion_type": "BINARY",
            "description": "Original criterion",
            "completion_conditions": "Original conditions",
        }
        criterion_version = app.db.models.GoalCriterionVersionDB(
            id="criterion-version-1",
            criterion_id=criterion.id,
            version=1,
            criterion_type=GoalCriterionType.BINARY,
            definition=definition,
            approval_status=GoalCriterionApprovalStatus.PROPOSED,
            created_by_user_id="owner-1",
            created_at=now,
        )
        session.add(criterion_version)
        version = GoalRepository(session).add_version(goal, "owner-1")

        assert version.content["criterion_versions"][0]["version_id"] == criterion_version.id
        assert version.content["criterion_versions"][0]["definition"]["description"] == "Original criterion"

        goal.structured_fields["deliverables"].append("Later change")
        criterion_version.definition["description"] = "Later change"
        assert "Later change" not in version.content["structured_fields"]["deliverables"]
        assert version.content["criterion_versions"][0]["definition"]["description"] == "Original criterion"
    finally:
        session.close()
        engine.dispose()


def test_goal_version_snapshots_organization_and_active_milestone_definitions():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        now = datetime.now(UTC)
        session.add(
            OrganizationDB(
                id="org-1",
                name="Example",
                normalized_name="example",
                created_at=now,
            )
        )
        session.add_all(
            [
                MilestoneDB(
                    id="milestone-1",
                    goal_id=goal.id,
                    title="Ship the release",
                    description="Release to users",
                    completion_criteria="The release is available",
                    status=MilestoneStatus.IN_PROGRESS,
                    source=MilestoneSource.MANUAL,
                    due_date=date(2027, 3, 15),
                    created_at=now,
                    updated_at=now,
                ),
                MilestoneDB(
                    id="archived-milestone",
                    goal_id=goal.id,
                    title="Old milestone",
                    status=MilestoneStatus.COMPLETED,
                    source=MilestoneSource.MANUAL,
                    archived_at=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.flush()
        repository = GoalRepository(session)
        repository.update(
            goal.id,
            {"organization_id": "org-1", "title": "Deliver the revised onboarding refresh"},
            changed_by_user_id="owner-1",
        )
        version = repository.get_latest_version(goal.id)
        assert version.content["organization_id"] == "org-1"
        assert version.content["milestone_definitions"] == [
            {
                "milestone_id": "milestone-1",
                "title": "Ship the release",
                "description": "Release to users",
                "completion_criteria": "The release is available",
                "source": "manual",
                "due_date": "2027-03-15",
            }
        ]

        milestone = session.get(MilestoneDB, "milestone-1")
        milestone.title = "Updated release"
        milestone.status = MilestoneStatus.COMPLETED
        session.flush()
        session.expire(version)
        assert version.content["milestone_definitions"][0]["title"] == "Ship the release"
        assert "status" not in version.content["milestone_definitions"][0]

        assert goal.milestones
        milestone.title = "Pending definition"
        milestone.due_date = date(2027, 4, 1)
        next_version = repository.add_version(goal, "owner-1")
        assert next_version.content["milestone_definitions"][0]["title"] == "Pending definition"
        assert next_version.content["milestone_definitions"][0]["due_date"] == "2027-04-01"
        assert milestone.status == MilestoneStatus.COMPLETED
        assert version.content["milestone_definitions"][0]["title"] == "Ship the release"
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
        assert first.rule_set_version == "goal-rules-v2"
        assert first.prompt_version == "goal-semantic-validation-v3"
        assert first.model_provider == "test-provider"
        assert first.model_version == "test-model"
        assert first.actor_user_id == "owner-1"
        assert {run.id for run in history} == {first.id, second.id}
    finally:
        session.close()
        engine.dispose()


def test_validate_exact_proposal_preserves_current_goal_and_eligibility():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        validation = GoalValidationRunService(session, _StructuredLLM())
        current_run = asyncio.run(validation.validate_latest(goal.id, "owner-1"))
        goals = GoalService(session)
        goals.transition_status(goal.id, GoalStatus.APPROVED, changed_by_user_id="owner-1")
        goals.transition_status(goal.id, GoalStatus.ACTIVE, changed_by_user_id="owner-1")
        proposal = _add_proposal(session, goal, 2, "Deliver the revised onboarding refresh")

        run = asyncio.run(validation.validate_proposal(goal.id, proposal.id, "owner-1"))

        assert run.status == "READY"
        assert run.goal_version_id == proposal.id
        assert run.input_context["title"] == "Deliver the revised onboarding refresh"
        assert goal.title == "Deliver onboarding refresh"
        assert goals.is_evidence_submission_eligible(goal)
        assert goals.repository.has_ready_validation_for_version(goal.id, current_run.goal_version_id)
        assert not goals.repository.has_approval_for_version(proposal.id)
        assert goals.repository.get_latest_version(goal.id).id == current_run.goal_version_id
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize(
    "case", ["wrong-owner", "missing-goal", "standard", "superseded", "legacy-proposal"]
)
def test_invalid_proposal_validation_is_rejected_before_provider_call(case):
    engine, session = _session()
    try:
        goal = _create_goal(session)
        proposal = _add_proposal(session, goal, 2, "Proposed title")
        if case == "superseded":
            _add_proposal(session, goal, 3, "Newer proposal")
        if case == "legacy-proposal":
            proposal.origin = "LEGACY"
            session.flush()

        class _CountingLLM(_StructuredLLM):
            calls = 0

            async def generate(self, request):
                self.calls += 1
                return await super().generate(request)

        llm = _CountingLLM()
        validation = GoalValidationRunService(session, llm)
        goal_id = "missing-goal" if case == "missing-goal" else goal.id
        proposal_id = (
            GoalRepository(session).get_latest_version(goal.id).id
            if case == "standard"
            else proposal.id
        )
        actor_id = "other-user" if case == "wrong-owner" else "owner-1"
        with pytest.raises(ValueError, match="Goal proposal not found"):
            asyncio.run(validation.validate_proposal(goal_id, proposal_id, actor_id))

        assert llm.calls == 0
        assert validation.get_history(goal.id) == []
    finally:
        session.close()
        engine.dispose()


def test_proposal_validation_provider_failure_does_not_persist_a_run():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        proposal = _add_proposal(session, goal, 2, "Proposed title")
        validation = GoalValidationRunService(session, _FailedLLM())
        with pytest.raises(GoalSemanticValidationError):
            asyncio.run(validation.validate_proposal(goal.id, proposal.id, "owner-1"))
        assert validation.get_history(goal.id) == []
    finally:
        session.close()
        engine.dispose()


def test_new_proposal_during_validation_retains_result_only_for_old_proposal():
    engine, session = _session()
    try:
        goal = _create_goal(session)
        proposal = _add_proposal(session, goal, 2, "First proposal")

        class _EditingLLM(_StructuredLLM):
            async def generate(self, request):
                _add_proposal(session, goal, 3, "Second proposal")
                return await super().generate(request)

        validation = GoalValidationRunService(session, _EditingLLM())
        with pytest.raises(ValueError, match="proposal changed during validation"):
            asyncio.run(validation.validate_proposal(goal.id, proposal.id, "owner-1"))

        history = validation.get_history(goal.id)
        assert len(history) == 1
        assert history[0].goal_version_id == proposal.id
        latest = GoalRepository(session).get_latest_proposal_version(goal.id)
        assert latest.version == 3
        assert not GoalRepository(session).has_ready_validation_for_version(goal.id, latest.id)
        assert goal.title == "Deliver onboarding refresh"
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
        assert record.prompt_version == "goal-semantic-validation-v3"
        assert "onboarding" not in str(record.__dict__)
    finally:
        session.close()
        engine.dispose()
