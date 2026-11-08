from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.evidence import (
    get_evidence_mapping_service,
    get_evidence_service,
    get_goal_service,
    get_milestone_service,
)
from app.db.base import Base
from app.db.models.goal import GoalDB
from app.db.models.goal_validation_run import GoalValidationRunDB
from app.db.models.goal_version import GoalVersionDB
from app.db.models.goal_version_approval import GoalVersionApprovalDB
from app.main import app
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.services.goal import GoalService

client = TestClient(app)


def test_newer_non_ready_run_blocks_evidence_despite_previous_ready(monkeypatch):
    session = _session_with_goal(validation_version=1)
    previous = session.get(GoalValidationRunDB, "run-1")
    session.add(
        GoalValidationRunDB(
            id="run-2",
            goal_id="goal-1",
            goal_version_id="version-1",
            status="NEEDS_REVIEW",
            findings=[],
            rule_set_version="rules-v1",
            prompt_version="prompt-v1",
            actor_user_id="user-1",
            created_at=previous.created_at + timedelta(seconds=1),
        )
    )
    session.flush()
    try:
        eligibility = _get_evidence_eligibility(session, monkeypatch)
        response, evidence_service, mapping_service = _post_evidence(session, monkeypatch)
    finally:
        session.close()
    assert eligibility.status_code == 200
    assert eligibility.json()["eligible"] is False
    assert eligibility.json()["ready_validation_exists"] is False
    assert response.status_code == 409
    evidence_service.create_evidence.assert_not_called()
    mapping_service.create_mapping.assert_not_called()


def _session_with_goal(
    *,
    status: GoalStatus = GoalStatus.ACTIVE,
    version_origins: tuple[str, ...] = ("USER",),
    validation_version: int | None = None,
    validation_status: str = "READY",
) -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            GoalDB.__table__,
            GoalVersionDB.__table__,
            GoalValidationRunDB.__table__,
            GoalVersionApprovalDB.__table__,
        ],
    )
    session = Session(engine)
    now = datetime.now(UTC)
    session.add(
        GoalDB(
            id="goal-1",
            user_id="user-1",
            title="Architecture",
            scope=GoalScope.PERSONAL,
            status=status,
            sub_status=(
                GoalSubStatus.NEEDS_REVIEW
                if status == GoalStatus.DRAFT
                else GoalSubStatus.ON_TRACK
            ),
            structured_fields={},
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    versions = []
    for version, origin in enumerate(version_origins, start=1):
        row = GoalVersionDB(
            id=f"version-{version}",
            goal_id="goal-1",
            version=version,
            origin=origin,
            content={"title": "Architecture"},
            created_by_user_id="user-1",
            created_at=now,
        )
        session.add(row)
        versions.append(row)
    session.flush()
    for version, origin in enumerate(version_origins, start=1):
        if origin == "USER":
            session.add(
                GoalVersionApprovalDB(
                    id=f"approval-{version}",
                    goal_id="goal-1",
                    goal_version_id=f"version-{version}",
                    actor_user_id="user-1",
                    created_at=now,
                )
            )
    session.flush()
    if validation_version is not None:
        session.add(
            GoalValidationRunDB(
                id="run-1",
                goal_id="goal-1",
                goal_version_id=versions[validation_version - 1].id,
                status=validation_status,
                findings=[],
                rule_set_version="rules-v1",
                prompt_version="prompt-v1",
                actor_user_id="user-1",
                created_at=now,
            )
        )
        session.flush()
    return session


def _post_evidence(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    legacy_validation_required: bool = False,
    user_id: str = "user-1",
):
    monkeypatch.setattr(
        "app.services.goal.get_settings",
        lambda: SimpleNamespace(
            require_validation_for_legacy_goal_evidence=legacy_validation_required
        ),
    )
    goal_service = GoalService(session)
    evidence_service = MagicMock()
    evidence_service.create_evidence.return_value = SimpleNamespace(
        id="evidence-1",
        title="Evidence",
        description=None,
        source_type=SimpleNamespace(value="personal"),
        source_url=None,
        captured_at=datetime.now(UTC),
        source_updated_at=None,
    )
    mapping_service = MagicMock()
    mapping_service.get_mappings_by_goal_id.return_value = []
    mapping_service.create_mapping.return_value = SimpleNamespace(
        id="mapping-1",
        milestone_id=None,
        relevance=SimpleNamespace(value="high"),
        confidence=1.0,
        reason="Added by the user",
    )
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.update(
        {
            get_goal_service: lambda: goal_service,
            get_evidence_service: lambda: evidence_service,
            get_evidence_mapping_service: lambda: mapping_service,
            get_milestone_service: lambda: MagicMock(),
        }
    )
    try:
        response = client.post(
            "/api/v1/goals/goal-1/evidence",
            params={"user_id": user_id},
            json={
                "title": "Evidence",
                "source_type": "personal",
                "captured_at": datetime.now(UTC).isoformat(),
                "relevance": "high",
                "validation_status": "READY",
            },
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
    return response, evidence_service, mapping_service


def _get_evidence_eligibility(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    legacy_validation_required: bool = False,
    user_id: str = "user-1",
):
    monkeypatch.setattr(
        "app.services.goal.get_settings",
        lambda: SimpleNamespace(
            require_validation_for_legacy_goal_evidence=legacy_validation_required
        ),
    )
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_goal_service] = lambda: GoalService(session)
    try:
        return client.get(
            "/api/v1/goals/goal-1/evidence-eligibility",
            params={"user_id": user_id},
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def test_evidence_eligibility_reports_active_ready_and_approved_goal(monkeypatch):
    session = _session_with_goal(validation_version=1)
    try:
        response = _get_evidence_eligibility(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 200
    assert response.json()["eligible"] is True
    assert response.json()["goal_status"] == "active"
    assert response.json()["ready_validation_exists"] is True
    assert response.json()["approved_for_latest_version"] is True


@pytest.mark.parametrize("goal_status", [GoalStatus.DRAFT, GoalStatus.APPROVED])
def test_evidence_eligibility_disallows_draft_and_pending_activation(
    monkeypatch, goal_status
):
    session = _session_with_goal(status=goal_status, validation_version=1)
    try:
        response = _get_evidence_eligibility(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 200
    assert response.json()["eligible"] is False
    assert "only active goals" in response.json()["reason"]


def test_evidence_eligibility_disallows_non_ready_validation(monkeypatch):
    session = _session_with_goal(
        validation_version=1,
        validation_status="NEEDS_IMPROVEMENT",
    )
    try:
        response = _get_evidence_eligibility(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 200
    assert response.json()["eligible"] is False
    assert response.json()["ready_validation_exists"] is False
    assert "READY validation" in response.json()["reason"]


def test_evidence_eligibility_disallows_unapproved_latest_version(monkeypatch):
    session = _session_with_goal(validation_version=1)
    session.query(GoalVersionApprovalDB).delete()
    session.flush()
    try:
        response = _get_evidence_eligibility(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 200
    assert response.json()["eligible"] is False
    assert response.json()["ready_validation_exists"] is True
    assert response.json()["approved_for_latest_version"] is False
    assert "must be approved" in response.json()["reason"]


def test_evidence_eligibility_reports_legacy_compatibility(monkeypatch):
    session = _session_with_goal(
        status=GoalStatus.DRAFT,
        version_origins=("LEGACY",),
    )
    try:
        response = _get_evidence_eligibility(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 200
    assert response.json()["eligible"] is True
    assert response.json()["legacy_compatibility"] is True
    assert "legacy compatibility" in response.json()["reason"]


def test_evidence_eligibility_is_owner_checked(monkeypatch):
    session = _session_with_goal(validation_version=1)
    try:
        response = _get_evidence_eligibility(
            session, monkeypatch, user_id="another-user"
        )
    finally:
        session.close()

    assert response.status_code == 404


def test_active_goal_with_persisted_ready_validation_can_submit_evidence(monkeypatch):
    session = _session_with_goal(validation_version=1)
    try:
        response, evidence_service, mapping_service = _post_evidence(
            session, monkeypatch
        )
    finally:
        session.close()

    assert response.status_code == 201
    evidence_service.create_evidence.assert_called_once()
    mapping_service.create_mapping.assert_called_once()


def test_draft_goal_pending_approval_cannot_submit_evidence(monkeypatch):
    session = _session_with_goal(status=GoalStatus.DRAFT, validation_version=1)
    try:
        response, evidence_service, mapping_service = _post_evidence(
            session, monkeypatch
        )
    finally:
        session.close()

    assert response.status_code == 409
    assert "active goal" in response.json()["error"]["message"]
    evidence_service.create_evidence.assert_not_called()
    mapping_service.create_mapping.assert_not_called()


def test_managed_goal_without_validation_cannot_submit_evidence(monkeypatch):
    session = _session_with_goal()
    try:
        response, evidence_service, _ = _post_evidence(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 409
    assert "READY validation run" in response.json()["error"]["message"]
    evidence_service.create_evidence.assert_not_called()


@pytest.mark.parametrize(
    "validation_status",
    ["NEEDS_IMPROVEMENT", "NEEDS_REVIEW", "INVALID"],
)
def test_non_ready_validation_cannot_submit_evidence(
    monkeypatch,
    validation_status,
):
    session = _session_with_goal(
        validation_version=1,
        validation_status=validation_status,
    )
    try:
        response, evidence_service, _ = _post_evidence(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 409
    evidence_service.create_evidence.assert_not_called()


def test_ready_validation_for_older_version_cannot_submit_evidence(monkeypatch):
    session = _session_with_goal(
        version_origins=("USER", "USER"),
        validation_version=1,
    )
    try:
        response, evidence_service, _ = _post_evidence(session, monkeypatch)
    finally:
        session.close()

    assert response.status_code == 409
    evidence_service.create_evidence.assert_not_called()


def test_non_owner_cannot_submit_evidence(monkeypatch):
    session = _session_with_goal(validation_version=1)
    try:
        response, evidence_service, mapping_service = _post_evidence(
            session,
            monkeypatch,
            user_id="other-user",
        )
    finally:
        session.close()

    assert response.status_code == 404
    evidence_service.create_evidence.assert_not_called()
    mapping_service.create_mapping.assert_not_called()


def test_legacy_goal_keeps_evidence_compatibility_by_default(monkeypatch):
    session = _session_with_goal(
        status=GoalStatus.DRAFT,
        version_origins=("LEGACY",),
    )
    try:
        response, evidence_service, mapping_service = _post_evidence(
            session, monkeypatch
        )
    finally:
        session.close()

    assert response.status_code == 201
    evidence_service.create_evidence.assert_called_once()
    mapping_service.create_mapping.assert_called_once()


def test_legacy_goal_requires_validation_in_strict_mode(monkeypatch):
    session = _session_with_goal(version_origins=("LEGACY",))
    try:
        response, evidence_service, _ = _post_evidence(
            session,
            monkeypatch,
            legacy_validation_required=True,
        )
    finally:
        session.close()

    assert response.status_code == 409
    evidence_service.create_evidence.assert_not_called()


def test_new_goal_remains_gated_when_legacy_validation_is_enabled(monkeypatch):
    session = _session_with_goal()
    try:
        response, evidence_service, _ = _post_evidence(
            session,
            monkeypatch,
            legacy_validation_required=True,
        )
    finally:
        session.close()

    assert response.status_code == 409
    evidence_service.create_evidence.assert_not_called()
