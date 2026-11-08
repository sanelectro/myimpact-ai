from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import evidence, goals
from app.auth import AuthenticatedUser, authorize_request_user, get_current_user
from app.main import app
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus

OPERATIONS = (
    ("POST", "validate"),
    ("GET", "validation-history"),
    ("GET", "requirements"),
    ("GET", "evidence-eligibility"),
    ("POST", "evidence"),
)


@pytest.fixture
def authorized_routes():
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.pop(authorize_request_user, None)
    current_user = AuthenticatedUser(
        "owner-1", "owner@example.test", None, {"myimpact-ai"}
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    now = datetime.now(UTC)
    goal_service = MagicMock()
    goal_service.get_goal_by_id.return_value = SimpleNamespace(
        user_id="owner-1",
        scope=GoalScope.PERSONAL,
        status=GoalStatus.ACTIVE,
        sub_status=GoalSubStatus.ON_TRACK,
    )
    goal_service.is_evidence_submission_eligible.return_value = True
    goal_service.get_evidence_submission_eligibility.return_value = {
        "eligible": True,
        "reason": "Ready for evidence.",
        "goal_status": "active",
        "latest_version": 1,
        "latest_version_origin": "USER",
        "legacy_compatibility": False,
        "ready_validation_exists": True,
        "approved_for_latest_version": True,
    }
    run = SimpleNamespace(
        id="run-1",
        goal_id="goal-1",
        goal_version_id="version-1",
        goal_version=SimpleNamespace(version=1),
        status="READY",
        findings=[],
        rule_set_version="rules-v1",
        prompt_version="prompt-v1",
        model_provider="mock",
        model_version="mock-model",
        actor_user_id="owner-1",
        created_at=now,
    )
    validation_service = MagicMock()
    validation_service.validate_latest = AsyncMock(return_value=run)
    validation_service.get_history.return_value = [run]
    validation_service.get_requirements.return_value = {
        "goal_version": 1,
        "evaluated_on": "2026-11-08",
        "requirements": [
            {"requirement": "target", "classification": "DEFERRED_ALLOWED", "state": "DEFERRED"}
        ],
        "deferred_requirements": [
            {"requirement": "target", "reason": "Await agreement", "resolution_stage": "Planning"}
        ],
    }
    evidence_service = MagicMock()
    evidence_service.create_evidence.return_value = SimpleNamespace(
        id="evidence-1",
        title="Evidence",
        description=None,
        source_type=SimpleNamespace(value="personal"),
        source_url=None,
        captured_at=now,
        source_updated_at=None,
    )
    mapping_service = MagicMock()
    mapping_service.get_mappings_by_goal_id.return_value = []
    mapping_service.create_mapping.return_value = SimpleNamespace(
        id="mapping-1",
        milestone_id=None,
        relevance=SimpleNamespace(value="high"),
        confidence=1.0,
        reason="Added by owner.",
    )
    app.dependency_overrides.update(
        {
            goals.get_goal_service: lambda: goal_service,
            goals.get_goal_validation_service: lambda: validation_service,
            evidence.get_goal_service: lambda: goal_service,
            evidence.get_evidence_service: lambda: evidence_service,
            evidence.get_evidence_mapping_service: lambda: mapping_service,
            evidence.get_milestone_service: lambda: MagicMock(),
        }
    )
    try:
        with TestClient(app) as client:
            yield client, current_user, goal_service, validation_service, evidence_service
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _request(client, method, operation, user_id="owner-1", **kwargs):
    if operation == "evidence":
        kwargs.setdefault(
            "json",
            {
                "title": "Evidence",
                "source_type": "personal",
                "captured_at": datetime.now(UTC).isoformat(),
                "relevance": "high",
            },
        )
    params = kwargs.pop("params", {"user_id": user_id})
    return client.request(
        method,
        f"/api/v1/goals/goal-1/{operation}",
        params=params,
        **kwargs,
    )


@pytest.mark.parametrize(("method", "operation"), OPERATIONS)
def test_authenticated_owner_can_use_validation_and_evidence_routes(
    authorized_routes, method, operation
):
    client, _, _, validation_service, evidence_service = authorized_routes
    response = _request(client, method, operation)
    assert response.status_code == (201 if method == "POST" else 200)
    if operation == "validate":
        validation_service.validate_latest.assert_awaited_once_with("goal-1", "owner-1")
        assert response.json()["actor_user_id"] == "owner-1"
    elif operation == "requirements":
        validation_service.get_requirements.assert_called_once_with("goal-1")
        assert response.json()["requirements"][0]["state"] == "DEFERRED"
    elif operation == "evidence":
        assert evidence_service.create_evidence.call_args.args[0].user_id == "owner-1"


@pytest.mark.parametrize(("method", "operation"), OPERATIONS)
@pytest.mark.parametrize("is_platform_admin", [False, True])
def test_spoofed_owner_is_rejected_before_services_run(
    authorized_routes, method, operation, is_platform_admin
):
    client, current_user, goal_service, validation_service, evidence_service = authorized_routes
    current_user.user_id = "other-user"
    current_user.is_platform_admin = is_platform_admin
    response = _request(client, method, operation)
    assert response.status_code == 403
    goal_service.get_goal_by_id.assert_not_called()
    validation_service.validate_latest.assert_not_called()
    validation_service.get_history.assert_not_called()
    validation_service.get_requirements.assert_not_called()
    evidence_service.create_evidence.assert_not_called()


@pytest.mark.parametrize(("method", "operation"), OPERATIONS)
def test_authenticated_user_cannot_access_goal_owned_by_someone_else(
    authorized_routes, method, operation
):
    client, _, goal_service, validation_service, evidence_service = authorized_routes
    goal_service.get_goal_by_id.return_value.user_id = "other-user"
    response = _request(client, method, operation)
    assert response.status_code == 404
    validation_service.validate_latest.assert_not_called()
    validation_service.get_history.assert_not_called()
    validation_service.get_requirements.assert_not_called()
    evidence_service.create_evidence.assert_not_called()


@pytest.mark.parametrize(("method", "operation"), OPERATIONS)
def test_validation_and_evidence_routes_require_authentication(
    authorized_routes, method, operation
):
    client, _, goal_service, _, _ = authorized_routes
    app.dependency_overrides.pop(get_current_user)
    response = _request(client, method, operation)
    assert response.status_code == 401
    goal_service.get_goal_by_id.assert_not_called()


@pytest.mark.parametrize(("method", "operation"), OPERATIONS)
def test_conflicting_query_user_ids_are_rejected(authorized_routes, method, operation):
    client, _, goal_service, _, _ = authorized_routes
    response = _request(
        client,
        method,
        operation,
        params=[("user_id", "other-user"), ("user_id", "owner-1")],
    )
    assert response.status_code == 403
    goal_service.get_goal_by_id.assert_not_called()
