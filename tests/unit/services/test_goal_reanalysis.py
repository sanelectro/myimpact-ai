import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, String, Table, create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.db.models
from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_approval import EvidenceApprovalDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.goal import GoalDB
from app.db.models.goal_source_retrieval import GoalSourceRetrievalDB
from app.db.models.goal_source_fetch_state import GoalSourceFetchStateDB
from app.db.models.goal_criterion import (
    GoalAssessmentRunDB,
    GoalCriterionAssessmentDB,
    GoalCriterionAssessmentEventDB,
    GoalCriterionAssessmentEvidenceDB,
    GoalCriterionDB,
    GoalCriterionVersionDB,
)
from app.db.models.milestone import MilestoneDB
from app.db.models.user import UserDB
from app.models.evidence import EvidenceSourceType, EvidenceStatus
from app.models.evidence_approval import EvidenceApprovalStatus
from app.models.evidence_mapping import EvidenceRelevance
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.models.goal_criteria import (
    GoalAssessmentLifecycle,
    GoalCriterionApprovalStatus,
    GoalCriterionDefinition,
    GoalCriterionResult,
    GoalCriterionType,
)
from app.services import goal_assessment as goal_assessment_module
from app.services.goal_assessment import GoalAssessmentService
from app.services.source_connections import SourceConnectionError


@pytest.fixture
def assessment_session():
    teams = Base.metadata.tables.get("teams")
    created_teams_table = teams is None
    if teams is None:
        teams = Table("teams", Base.metadata, Column("id", String(64), primary_key=True))

    engine = create_engine("sqlite://")
    now = datetime.now(UTC)
    tables = [
        teams,
        UserDB.__table__,
        GoalDB.__table__,
        MilestoneDB.__table__,
        EvidenceDB.__table__,
        EvidenceVersionDB.__table__,
        EvidenceMappingDB.__table__,
        EvidenceApprovalDB.__table__,
        GoalSourceFetchStateDB.__table__,
        GoalCriterionDB.__table__,
        GoalCriterionVersionDB.__table__,
        GoalAssessmentRunDB.__table__,
        GoalSourceRetrievalDB.__table__,
        GoalCriterionAssessmentDB.__table__,
        GoalCriterionAssessmentEvidenceDB.__table__,
        GoalCriterionAssessmentEventDB.__table__,
    ]
    try:
        Base.metadata.create_all(engine, tables=tables)
        with Session(engine) as session:
            user = UserDB(
                id="test-user",
                name="Test User",
                email="test@example.test",
                created_at=now,
                updated_at=now,
            )
            goal = GoalDB(
                id="test-goal",
                user_id=user.id,
                title="Improve deployment reliability",
                description="Reduce failed deployments through safer releases.",
                scope=GoalScope.PERSONAL,
                status=GoalStatus.ACTIVE,
                sub_status=GoalSubStatus.ON_TRACK,
                start_date=(now - timedelta(days=1000)).date(),
                created_at=now,
                updated_at=now,
            )
            definition = GoalCriterionDefinition(
                criterion_type=GoalCriterionType.BINARY,
                description="Enable production canary validation",
                completion_conditions="Canary validation is enabled and verified in production.",
            )
            criterion = GoalCriterionDB(
                id="test-criterion",
                goal_id=goal.id,
                current_version=1,
                is_retired=False,
                created_by_user_id=user.id,
                created_at=now,
                updated_at=now,
            )
            criterion_version = GoalCriterionVersionDB(
                id="test-criterion-version",
                criterion_id=criterion.id,
                version=1,
                criterion_type=definition.criterion_type,
                definition=definition.model_dump(mode="json"),
                approval_status=GoalCriterionApprovalStatus.APPROVED,
                created_by_user_id=user.id,
                approved_by_user_id=user.id,
                approved_at=now,
                created_at=now,
            )
            session.add_all([user, goal, criterion, criterion_version])
            session.commit()
            yield session
    finally:
        engine.dispose()
        if created_teams_table and teams is not None:
            Base.metadata.remove(teams)


def test_reanalysis_refreshes_sources_versions_evidence_and_reports_partial_failure(
    assessment_session,
    monkeypatch,
):
    assert app.db.models.GoalDB is GoalDB
    session = assessment_session
    now = datetime.now(UTC)
    candidate_versions = [
        {
            "source_type": "github",
            "source_id": "acme/app#7",
            "title": "Canary deployment support",
            "description": "Implemented and verified the production canary release path.",
            "summary": "The pull request implements the production canary release path.",
            "source_url": "https://github.com/acme/app/pull/7",
            "captured_at": now - timedelta(days=2),
            "source_updated_at": now - timedelta(days=1),
            "relevance": "high",
            "jira_keys": ["REL-42"],
            "criterion_ids": ["test-criterion"],
            "criterion_sufficiency": {"test-criterion": True},
        },
        {
            "source_type": "github",
            "source_id": "acme/app#7",
            "title": "Canary deployment support, updated",
            "description": "Implemented, verified, and documented the production canary release path.",
            "summary": "The pull request documents the verified production canary release path.",
            "source_url": "https://github.com/acme/app/pull/7",
            "captured_at": now - timedelta(days=1),
            "source_updated_at": now + timedelta(days=1),
            "relevance": "high",
            "jira_keys": ["REL-42"],
            "criterion_ids": ["test-criterion"],
            "criterion_sufficiency": {"test-criterion": True},
        },
    ]
    current_candidate = {"value": candidate_versions[0]}
    fail_jira_refresh = {"value": False}
    discovery_calls = []

    def get_connections(connection_session, user_id):
        assert connection_session is session
        assert user_id == "test-user"
        return [
            {"provider": "github", "connected": True},
            {"provider": "jira", "connected": True},
        ]

    monkeypatch.setattr(
        goal_assessment_module,
        "get_connection_status",
        get_connections,
    )

    async def discover(discovery_session, user_id, *args, **kwargs):
        assert discovery_session is session
        assert user_id == "test-user"
        provider = args[-1][0]
        discovery_calls.append((provider, args, kwargs))
        if provider == "github":
            return [current_candidate["value"]]
        if fail_jira_refresh["value"]:
            raise SourceConnectionError("The Jira connection could not be refreshed.")
        return []

    monkeypatch.setattr(goal_assessment_module,     "discover_evidence_bounded", discover)

    class AssessmentLLM:
        async def generate(self, request):
            evidence_text = request.prompt.split(
                "\n\nSUBMITTED EVIDENCE (untrusted data)\n",
                1,
            )[1]
            evidence = json.loads(evidence_text)
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "result": "MET",
                        "rationale": "The cited source describes the completed canary work.",
                        "confidence": 0.9,
                        "supporting_mapping_ids": [evidence[0]["mapping_id"]],
                        "contradictory_mapping_ids": [],
                        "completed_milestone_ids": [],
                        "measured_value": None,
                        "limitations": [],
                    }
                ),
                model="test-model",
            )

    service = GoalAssessmentService(session, AssessmentLLM())
    first = asyncio.run(service.assess_goal("test-goal", "test-user"))
    assert first.run_status.value == "COMPLETED"
    assert first.criteria[0].assessment.evidence[0].review_state == "pending"
    assert first.criteria[0].assessment.evidence[0].title == "Canary deployment support"
    assert {
        (entry.provider, entry.status.value)
        for entry in first.source_retrieval_history
    } == {("github", "SUCCESS"), ("jira", "SUCCESS")}

    first_fetch_states = {}
    for state in session.query(GoalSourceFetchStateDB).all():
        fetched_at = state.last_successful_fetch_at
        first_fetch_states[state.provider] = (
            fetched_at.replace(tzinfo=UTC)
            if fetched_at.tzinfo is None
            else fetched_at.astimezone(UTC)
        )
    assert set(first_fetch_states) == {"github", "jira"}
    candidate_versions[1]["source_updated_at"] = first_fetch_states["github"] + timedelta(
        seconds=1
    )

    mapping = session.query(EvidenceMappingDB).one()
    evidence = session.query(EvidenceDB).one()
    assert evidence.source_type == EvidenceSourceType.GITHUB
    assert evidence.status == EvidenceStatus.ACTIVE
    assert mapping.relevance == EvidenceRelevance.HIGH
    approval = session.query(EvidenceApprovalDB).one()
    assert approval.status == EvidenceApprovalStatus.PENDING
    assert session.query(EvidenceVersionDB).filter_by(evidence_id=evidence.id).count() == 1

    current_candidate["value"] = candidate_versions[1]
    fail_jira_refresh["value"] = True
    second = asyncio.run(service.assess_goal("test-goal", "test-user"))

    assert second.run_status.value == "PARTIAL"
    assert "Jira evidence refresh failed" in second.run_error_message
    jira_failure = next(
        entry
        for entry in second.source_retrieval_history
        if entry.run_id == second.run_id and entry.provider == "jira"
    )
    assert jira_failure.status.value == "FAILURE"
    assert "could not be refreshed" in jira_failure.failure_reason
    assert jira_failure.used_snapshot is False
    assert second.criteria[0].assessment.result == GoalCriterionResult.MET
    assert second.criteria[0].assessment.evidence[0].title == "Canary deployment support, updated"
    assert session.query(EvidenceMappingDB).count() == 1
    assert session.query(EvidenceVersionDB).filter_by(evidence_id=evidence.id).count() == 2
    second_fetch_states = {}
    for state in session.query(GoalSourceFetchStateDB).all():
        fetched_at = state.last_successful_fetch_at
        second_fetch_states[state.provider] = (
            fetched_at.replace(tzinfo=UTC)
            if fetched_at.tzinfo is None
            else fetched_at.astimezone(UTC)
        )
    assert second_fetch_states["github"] > first_fetch_states["github"]
    assert second_fetch_states["jira"] == first_fetch_states["jira"]
    previous_assessment = (
        session.query(GoalCriterionAssessmentDB)
        .filter(GoalCriterionAssessmentDB.id == first.criteria[0].assessment.id)
        .one()
    )
    assert previous_assessment.lifecycle_state == GoalAssessmentLifecycle.OBSOLETE
    assert previous_assessment.evidence[0].title_snapshot == "Canary deployment support"
    assert len(discovery_calls) == 4
    github_options = discovery_calls[2][2]
    jira_options = discovery_calls[3][2]
    assert github_options["max_github_commits"] == 10
    assert github_options["max_github_pull_request_lookups"] == 5
    assert github_options["max_candidates"] == 20
    assert github_options["criteria"][0]["criterion_id"] == "test-criterion"
    assert "production canary validation" in github_options["criteria"][0]["search_text"]
    assert jira_options["jira_keys"] == {"REL-42"}
    assert github_options["after"] == first_fetch_states["github"]
    assert jira_options["after"] == first_fetch_states["jira"]
    start_date = discovery_calls[-1][1][-3]
    end_date = discovery_calls[-1][1][-2]
    assert (end_date - start_date).days + 1 <= 366
    assert start_date == first_fetch_states["jira"].date() - timedelta(days=1)

    fail_jira_refresh["value"] = False
    retry = asyncio.run(service.assess_goal("test-goal", "test-user"))
    assert retry.run_status.value == "COMPLETED"
    retried_fetch_states = {}
    for state in session.query(GoalSourceFetchStateDB).all():
        fetched_at = state.last_successful_fetch_at
        retried_fetch_states[state.provider] = (
            fetched_at.replace(tzinfo=UTC)
            if fetched_at.tzinfo is None
            else fetched_at.astimezone(UTC)
        )
    assert retried_fetch_states["jira"] > first_fetch_states["jira"]
    assert discovery_calls[5][2]["after"] == first_fetch_states["jira"]

    def no_connected_sources(connection_session, user_id):
        assert connection_session is session
        assert user_id == "test-user"
        return []

    monkeypatch.setattr(
        goal_assessment_module,
        "get_connection_status",
        no_connected_sources,
    )
    fourth = asyncio.run(service.assess_goal("test-goal", "test-user"))
    assert fourth.run_status.value == "PARTIAL"
    assert "GitHub is not connected" in fourth.run_error_message
    github_fallback = next(
        entry
        for entry in fourth.source_retrieval_history
        if entry.run_id == fourth.run_id and entry.provider == "github"
    )
    assert github_fallback.status.value == "FAILURE"
    assert github_fallback.used_snapshot is True
    assert github_fallback.snapshot_captured_at is not None
    assert fourth.criteria[0].assessment.result == GoalCriterionResult.MET
    assert fourth.criteria[0].assessment.evidence[0].title == "Canary deployment support, updated"
    assert len(discovery_calls) == 6


def test_reanalysis_scopes_new_evidence_to_the_criteria_it_matches(
    assessment_session,
    monkeypatch,
):
    session = assessment_session
    now = datetime.now(UTC)
    user = session.get(UserDB, "test-user")
    second_criterion = GoalCriterionDB(
        id="second-criterion",
        goal_id="test-goal",
        current_version=1,
        is_retired=False,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    second_definition = GoalCriterionDefinition(
        criterion_type=GoalCriterionType.BINARY,
        description="Publish service reliability dashboards",
        completion_conditions="Service dashboards are available to the on-call team.",
    )
    second_version = GoalCriterionVersionDB(
        id="second-criterion-version",
        criterion_id=second_criterion.id,
        version=1,
        criterion_type=second_definition.criterion_type,
        definition=second_definition.model_dump(mode="json"),
        approval_status=GoalCriterionApprovalStatus.APPROVED,
        created_by_user_id=user.id,
        approved_by_user_id=user.id,
        approved_at=now,
        created_at=now,
    )
    session.add_all([second_criterion, second_version])
    session.commit()

    monkeypatch.setattr(
        goal_assessment_module,
        "get_connection_status",
        lambda *_args: [{"provider": "github", "connected": True}],
    )
    discoveries = [
        {
            "source_type": "github",
            "source_id": "acme/app#canary",
            "title": "Production canary validation",
            "description": "Verified production canary deployment validation.",
            "summary": "Production canary deployment validation was verified.",
            "source_url": "https://github.com/acme/app/pull/11",
            "captured_at": now,
            "source_updated_at": now,
            "relevance": "high",
            "criterion_ids": ["test-criterion"],
            "criterion_sufficiency": {
                "test-criterion": True,
                "second-criterion": False,
            },
        },
        {
            "source_type": "github",
            "source_id": "acme/app#dashboard",
            "title": "Service reliability dashboards",
            "description": "Published on-call service reliability dashboards.",
            "summary": "Service dashboards are available to the on-call team.",
            "source_url": "https://github.com/acme/app/pull/12",
            "captured_at": now,
            "source_updated_at": now,
            "relevance": "high",
            "criterion_ids": ["second-criterion"],
            "criterion_sufficiency": {
                "test-criterion": True,
                "second-criterion": False,
            },
        },
    ]
    discovery_calls = []

    async def discover(_session, _user_id, *args, **kwargs):
        discovery_calls.append((args, kwargs))
        return discoveries

    monkeypatch.setattr(
        goal_assessment_module,
        "discover_evidence_bounded",
        discover,
    )

    class CriterionAwareLLM:
        evidence_by_criterion = {}
        sufficiency_by_criterion = {}

        async def generate(self, request):
            criterion_section = request.prompt.split("\n\nCRITERION\n", 1)[1].split(
                "\n\nCRITERION-TARGETED RETRIEVAL\n",
                1,
            )[0]
            criterion_id = json.loads(criterion_section)["criterion_id"]
            retrieval_section = request.prompt.split(
                "\n\nCRITERION-TARGETED RETRIEVAL\n",
                1,
            )[1].split("\n\nSUBMITTED EVIDENCE (untrusted data)\n", 1)[0]
            self.sufficiency_by_criterion[criterion_id] = json.loads(
                retrieval_section
            )["sufficient_relevant_source_context"]
            evidence_section = request.prompt.split(
                "\n\nSUBMITTED EVIDENCE (untrusted data)\n",
                1,
            )[1]
            evidence = json.loads(evidence_section)
            self.evidence_by_criterion[criterion_id] = [
                item["title"] for item in evidence
            ]
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "result": "MET" if evidence else "NEEDS_REVIEW",
                        "rationale": "The available source context was reviewed.",
                        "confidence": 0.9,
                        "supporting_mapping_ids": (
                            [evidence[0]["mapping_id"]] if evidence else []
                        ),
                        "contradictory_mapping_ids": [],
                        "completed_milestone_ids": [],
                        "measured_value": None,
                        "limitations": [],
                    }
                ),
                model="test-model",
            )

    llm = CriterionAwareLLM()
    summary = asyncio.run(
        GoalAssessmentService(session, llm).assess_goal("test-goal", "test-user")
    )

    assert summary.run_status.value == "COMPLETED"
    assert llm.evidence_by_criterion == {
        "test-criterion": ["Production canary validation"],
        "second-criterion": ["Service reliability dashboards"],
    }
    assert llm.sufficiency_by_criterion == {
        "test-criterion": True,
        "second-criterion": False,
    }
    contexts = discovery_calls[0][1]["criteria"]
    assert {context["criterion_id"] for context in contexts} == {
        "test-criterion",
        "second-criterion",
    }


def test_reanalysis_skips_approved_criteria_when_goal_has_no_evidence(
    assessment_session,
    monkeypatch,
):
    session = assessment_session
    monkeypatch.setattr(
        goal_assessment_module,
        "get_connection_status",
        lambda *_args: [],
    )

    class NeverCalledLLM:
        async def generate(self, _request):
            raise AssertionError("An assessment must not run without evidence.")

    summary = asyncio.run(
        GoalAssessmentService(session, NeverCalledLLM()).assess_goal(
            "test-goal",
            "test-user",
        )
    )

    assert summary.run_status.value == "COMPLETED"
    assert summary.assessed_criteria_count == 0
    assert session.query(GoalCriterionAssessmentDB).count() == 0


def test_reanalysis_skips_unapproved_criteria_even_when_evidence_is_attached(
    assessment_session,
    monkeypatch,
):
    session = assessment_session
    now = datetime.now(UTC)
    version = session.query(GoalCriterionVersionDB).one()
    version.approval_status = GoalCriterionApprovalStatus.PROPOSED
    evidence = EvidenceDB(
        id="unapproved-criterion-evidence",
        user_id="test-user",
        source_type=EvidenceSourceType.GITHUB,
        source_id="acme/app#8",
        title="Production canary change",
        description="Enabled the production canary release path.",
        source_url="https://github.com/acme/app/pull/8",
        captured_at=now,
        source_updated_at=now,
        content_hash="evidence-content-hash",
        status=EvidenceStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    mapping = EvidenceMappingDB(
        id="unapproved-criterion-mapping",
        evidence_id=evidence.id,
        goal_id="test-goal",
        milestone_id=None,
        relevance=EvidenceRelevance.HIGH,
        reason="Supports the goal.",
        confidence=1.0,
        created_at=now,
        updated_at=now,
    )
    session.add_all([evidence, mapping])
    session.commit()

    monkeypatch.setattr(
        goal_assessment_module,
        "get_connection_status",
        lambda *_args: [{"provider": "github", "connected": True}],
    )

    async def discover(*_args, **_kwargs):
        return []

    monkeypatch.setattr(goal_assessment_module, "discover_evidence_bounded", discover)

    class NeverCalledLLM:
        async def generate(self, _request):
            raise AssertionError("An unapproved criterion must not be assessed.")

    summary = asyncio.run(
        GoalAssessmentService(session, NeverCalledLLM()).assess_goal(
            "test-goal",
            "test-user",
        )
    )

    assert summary.run_status.value == "COMPLETED"
    assert summary.assessed_criteria_count == 0
    assert session.query(GoalCriterionAssessmentDB).count() == 0
