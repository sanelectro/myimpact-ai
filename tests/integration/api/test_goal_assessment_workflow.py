import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, String, Table, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.db.models
from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_approval import EvidenceApprovalDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.goal import GoalDB
from app.db.models.goal_source_fetch_state import GoalSourceFetchStateDB
from app.db.models.goal_source_retrieval import GoalSourceRetrievalDB
from app.db.models.goal_criterion import (
    GoalAssessmentRunDB,
    GoalCriterionAssessmentDB,
    GoalCriterionAssessmentEvidenceDB,
    GoalCriterionAssessmentEventDB,
    GoalCriterionDB,
    GoalCriterionVersionDB,
)
from app.db.models.user import UserDB
from app.db.session import get_db
from app.main import app
from app.models.evidence import EvidenceSourceType, EvidenceStatus
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.models.evidence_mapping import EvidenceRelevance
from app.models.goal_criteria import (
    GoalAssessmentLifecycle,
    GoalAssessmentRunStatus,
    GoalCriterionApprovalStatus,
    GoalCriterionDefinition,
    GoalCriterionResult,
    GoalCriterionType,
)
from app.services.goal_assessment import GoalAssessmentService
from app.services import goal_assessment as goal_assessment_module
from app.services.source_connections import SourceConnectionError


@pytest.mark.integration
def test_feedback_and_criterion_revision_preserve_assessment_history():
    teams = Base.metadata.tables.get("teams")
    created_teams_table = teams is None
    if teams is None:
        teams = Table("teams", Base.metadata, Column("id", String(64), primary_key=True))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    now = datetime.now(UTC)
    tables = [
        teams,
        UserDB.__table__,
        GoalDB.__table__,
        EvidenceDB.__table__,
        EvidenceVersionDB.__table__,
        EvidenceMappingDB.__table__,
        GoalCriterionDB.__table__,
        GoalCriterionVersionDB.__table__,
        GoalAssessmentRunDB.__table__,
        GoalCriterionAssessmentDB.__table__,
        GoalCriterionAssessmentEvidenceDB.__table__,
        GoalCriterionAssessmentEventDB.__table__,
        GoalSourceFetchStateDB.__table__,
        GoalSourceRetrievalDB.__table__,
    ]
    previous_db_override = app.dependency_overrides.get(get_db)
    try:
        Base.metadata.create_all(engine, tables=tables)
        with Session(engine) as session:
            user = UserDB(
                id="workflow-user",
                name="Workflow User",
                email="workflow@example.test",
                created_at=now,
                updated_at=now,
            )
            goal = GoalDB(
                id="workflow-goal",
                user_id=user.id,
                title="Improve deployment reliability",
                description="Reduce failed deployments through safer releases.",
                scope=GoalScope.PERSONAL,
                status=GoalStatus.ACTIVE,
                sub_status=GoalSubStatus.ON_TRACK,
                created_at=now,
                updated_at=now,
            )
            definition = GoalCriterionDefinition(
                criterion_type=GoalCriterionType.BINARY,
                description="Enable production canary validation",
                completion_conditions="Canary validation is enabled in production.",
            ).model_dump(mode="json")
            criterion = GoalCriterionDB(
                id="workflow-criterion",
                goal_id=goal.id,
                current_version=1,
                is_retired=False,
                created_by_user_id=user.id,
                created_at=now,
                updated_at=now,
            )
            version = GoalCriterionVersionDB(
                id="workflow-version-1",
                criterion_id=criterion.id,
                version=1,
                criterion_type=GoalCriterionType.BINARY,
                definition=definition,
                approval_status=GoalCriterionApprovalStatus.APPROVED,
                created_by_user_id=user.id,
                approved_by_user_id=user.id,
                approved_at=now,
                created_at=now,
            )
            run = GoalAssessmentRunDB(
                id="workflow-run",
                batch_id=None,
                goal_id=goal.id,
                requested_by_user_id=user.id,
                status=GoalAssessmentRunStatus.COMPLETED,
                trigger="MANUAL",
                created_at=now,
                started_at=now,
                finished_at=now,
            )
            assessment = GoalCriterionAssessmentDB(
                id="workflow-assessment",
                run_id=run.id,
                criterion_id=criterion.id,
                criterion_version_id=version.id,
                result=GoalCriterionResult.MET,
                lifecycle_state=GoalAssessmentLifecycle.CURRENT,
                progress_percentage=100,
                rationale="The source evidence supports the completion condition.",
                confidence=0.9,
                completed_milestone_ids=[],
                input_fingerprint=GoalAssessmentService._fingerprint(
                    version,
                    [],
                    goal,
                ),
                prompt_version="m66-criterion-assessment-v1",
                created_at=now,
            )
            session.add_all([user, goal, criterion, version, run, assessment])
            session.commit()

            def override_db():
                yield session

            app.dependency_overrides[get_db] = override_db
            client = TestClient(app)
            assessment_url = f"/api/v1/goals/{goal.id}/assessment"
            feedback_url = (
                f"/api/v1/goals/{goal.id}/criteria/{criterion.id}"
                f"/assessments/{assessment.id}/feedback"
            )
            initial = client.get(assessment_url, params={"user_id": user.id})
            assert initial.status_code == 200
            assert initial.json()["criteria"][0]["assessment"]["lifecycle_state"] == "CURRENT"

            unauthorized = client.post(
                feedback_url,
                params={"user_id": "another-user"},
                json={"feedback_type": "CONFIRMED"},
            )
            assert unauthorized.status_code == 404

            feedback = client.post(
                feedback_url,
                params={"user_id": user.id},
                json={
                    "feedback_type": "CORRECTED",
                    "corrected_result": "IN_PROGRESS",
                    "comment": "The source only confirms a partial rollout.",
                },
            )
            assert feedback.status_code == 200
            feedback_assessment = feedback.json()["criteria"][0]["assessment"]
            assert feedback_assessment["result"] == "MET"
            decision_event = next(
                event for event in feedback_assessment["events"]
                if event["event_type"] == "CORRECTED"
            )
            assert decision_event["actor_user_id"] == user.id
            assert decision_event["details"]["corrected_result"] == "IN_PROGRESS"

            revised = client.put(
                f"/api/v1/goals/{goal.id}/criteria/{criterion.id}",
                params={"user_id": user.id},
                json={
                    "definition": {
                        **definition,
                        "description": "Enable and verify production canary validation",
                    }
                },
            )
            assert revised.status_code == 200
            assert len(revised.json()["versions"]) == 2
            assert revised.json()["current_version"] == 1

            historical = client.get(assessment_url, params={"user_id": user.id})
            assert historical.status_code == 200
            preserved = historical.json()["criteria"][0]["assessment"]
            assert preserved["id"] == assessment.id
            assert preserved["result"] == "MET"
            assert preserved["lifecycle_state"] == "OBSOLETE"
            assert any(
                event["event_type"] == "LIFECYCLE_CHANGED"
                and event["lifecycle_state"] == "OBSOLETE"
                for event in preserved["events"]
            )
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override
        engine.dispose()
        if created_teams_table and teams is not None:
            Base.metadata.remove(teams)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("connection_state", "expected_failure_reason"),
    [
        (
            "unavailable",
            "Could not check connected sources: GitHub API quota exceeded.",
        ),
        (
            "missing",
            "GitHub is not connected; assessment uses stored evidence snapshots.",
        ),
    ],
)
def test_source_failure_is_persisted_and_api_preserves_stored_evidence(
    monkeypatch,
    connection_state,
    expected_failure_reason,
):
    teams = Base.metadata.tables.get("teams")
    created_teams_table = teams is None
    if teams is None:
        teams = Table("teams", Base.metadata, Column("id", String(64), primary_key=True))

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    now = datetime.now(UTC)
    tables = [
        teams,
        UserDB.__table__,
        GoalDB.__table__,
        EvidenceDB.__table__,
        EvidenceVersionDB.__table__,
        EvidenceApprovalDB.__table__,
        EvidenceMappingDB.__table__,
        GoalCriterionDB.__table__,
        GoalCriterionVersionDB.__table__,
        GoalAssessmentRunDB.__table__,
        GoalCriterionAssessmentDB.__table__,
        GoalCriterionAssessmentEvidenceDB.__table__,
        GoalCriterionAssessmentEventDB.__table__,
        GoalSourceFetchStateDB.__table__,
        GoalSourceRetrievalDB.__table__,
    ]
    previous_db_override = app.dependency_overrides.get(get_db)
    try:
        Base.metadata.create_all(engine, tables=tables)
        with Session(engine) as session:
            user = UserDB(
                id="source-failure-user",
                name="Source Failure User",
                email="source-failure@example.test",
                created_at=now,
                updated_at=now,
            )
            goal = GoalDB(
                id="source-failure-goal",
                user_id=user.id,
                title="Improve deployment reliability",
                description="Reduce failed deployments through safer releases.",
                scope=GoalScope.PERSONAL,
                status=GoalStatus.ACTIVE,
                sub_status=GoalSubStatus.ON_TRACK,
                created_at=now,
                updated_at=now,
            )
            evidence = EvidenceDB(
                id="source-snapshot",
                user_id=user.id,
                source_type=EvidenceSourceType.GITHUB,
                source_id="commit-123",
                title="Canary deployment support",
                description="Enabled and verified production canary releases.",
                source_url="https://github.example.test/commit/123",
                captured_at=now,
                source_updated_at=now,
                content_hash="snapshot-hash",
                status=EvidenceStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
            mapping = EvidenceMappingDB(
                id="source-snapshot-mapping",
                evidence_id=evidence.id,
                goal_id=goal.id,
                relevance=EvidenceRelevance.HIGH,
                reason="Stored evidence snapshot",
                confidence=1.0,
                created_at=now,
                updated_at=now,
            )
            run = GoalAssessmentRunDB(
                id="source-failure-run",
                batch_id=None,
                goal_id=goal.id,
                requested_by_user_id=user.id,
                status=GoalAssessmentRunStatus.COMPLETED,
                trigger="MANUAL",
                created_at=now,
                started_at=now,
                finished_at=now,
            )
            session.add_all([user, goal, evidence, mapping, run])
            session.commit()

            def fail_connection_check(*_args, **_kwargs):
                raise SourceConnectionError("GitHub API quota exceeded.")

            monkeypatch.setattr(
                goal_assessment_module,
                "get_connection_status",
                (lambda *_args, **_kwargs: [])
                if connection_state == "missing"
                else fail_connection_check,
            )
            result = asyncio.run(
                GoalAssessmentService(session)._refresh_goal_sources(
                    goal,
                    user.id,
                    [],
                    run.id,
                )
            )
            session.commit()

            retrieval = session.query(GoalSourceRetrievalDB).one()
            stored_evidence = session.get(EvidenceDB, evidence.id)
            assert retrieval.failure_reason == expected_failure_reason
            assert retrieval.status == "FAILURE"
            assert retrieval.used_snapshot is True
            assert retrieval.snapshot_captured_at.replace(tzinfo=UTC) == now
            assert stored_evidence.description == evidence.description
            assert stored_evidence.content_hash == evidence.content_hash
            assert not result.source_refreshed

            def override_db():
                yield session

            app.dependency_overrides[get_db] = override_db
            response = TestClient(app).get(
                f"/api/v1/goals/{goal.id}/assessment",
                params={"user_id": user.id},
            )

            assert response.status_code == 200
            source_history = response.json()["source_retrieval_history"]
            assert len(source_history) == 1
            assert source_history[0]["failure_reason"] == retrieval.failure_reason
            assert source_history[0]["used_snapshot"] is True
            assert source_history[0]["snapshot_captured_at"] is not None
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override
        engine.dispose()
        if created_teams_table and teams is not None:
            Base.metadata.remove(teams)
