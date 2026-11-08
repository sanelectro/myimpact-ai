from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.evidence import get_evidence_mapping_service, get_evidence_service, get_goal_service
from app.api.v1.goal_evidence_context import get_goal_evidence_context_service
from app.auth import AuthenticatedUser, authorize_request_user, get_current_user
from app.exceptions import EvidenceMappingAlreadyExistsError
from app.main import app
from app.models.evidence import EvidenceStatus
from app.models.evidence_mapping import EvidenceMappingKind


@pytest.fixture
def routes():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.pop(authorize_request_user, None)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "owner", "owner@example.test", None, {"myimpact-ai"}
    )
    goal_service, evidence_service, mapping_service, context_service = (MagicMock() for _ in range(4))
    goal_service.get_goal_by_id.return_value = SimpleNamespace(user_id="owner")
    goal_service.is_evidence_submission_eligible.return_value = True
    evidence_service.get_evidence_by_id.return_value = SimpleNamespace(
        id="evidence-1", user_id="owner", status=EvidenceStatus.ACTIVE
    )
    mapping_service.create_mapping.return_value = SimpleNamespace(
        id="mapping-1", mapping_kind="CONTRIBUTION", contribution_description="Supports parent"
    )
    context_service.get_context.return_value = {
        "items": [], "has_more": False, "next_offset": None, "hierarchy_truncated": False
    }
    app.dependency_overrides.update({
        get_goal_service: lambda: goal_service,
        get_evidence_service: lambda: evidence_service,
        get_evidence_mapping_service: lambda: mapping_service,
        get_goal_evidence_context_service: lambda: context_service,
    })
    try:
        with TestClient(app) as client:
            yield client, goal_service, evidence_service, mapping_service, context_service
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_link_existing_evidence_creates_owned_contribution(routes):
    client, _, _, mapping_service, _ = routes
    response = client.post(
        "/api/v1/goals/goal-1/evidence-links", params={"user_id": "owner"},
        json={"evidence_id": "evidence-1", "mapping_kind": "CONTRIBUTION",
              "contribution_description": "Supports parent", "relevance": "high"},
    )
    assert response.status_code == 201
    assert response.json()["mapping_id"] == "mapping-1"
    assert response.json()["approval_status"] == "pending"
    assert mapping_service.create_mapping.call_args.kwargs["created_by_user_id"] == "owner"
    assert mapping_service.create_mapping.call_args.kwargs["mapping_kind"] is EvidenceMappingKind.CONTRIBUTION


def test_link_rejects_unowned_evidence_and_ineligible_goal(routes):
    client, goal_service, evidence_service, mapping_service, _ = routes
    request = {"evidence_id": "evidence-1", "relevance": "high"}
    evidence_service.get_evidence_by_id.return_value.user_id = "other"
    assert client.post("/api/v1/goals/goal-1/evidence-links", params={"user_id": "owner"}, json=request).status_code == 404
    goal_service.is_evidence_submission_eligible.return_value = False
    assert client.post("/api/v1/goals/goal-1/evidence-links", params={"user_id": "owner"}, json=request).status_code == 409
    mapping_service.create_mapping.assert_not_called()


def test_duplicate_link_returns_conflict(routes):
    client, _, _, mapping_service, _ = routes
    mapping_service.create_mapping.side_effect = EvidenceMappingAlreadyExistsError("Already mapped")
    response = client.post(
        "/api/v1/goals/goal-1/evidence-links", params={"user_id": "owner"},
        json={"evidence_id": "evidence-1", "relevance": "high"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(("method", "path", "body"), [
    ("GET", "evidence-context", None),
    ("POST", "evidence-links", {"evidence_id": "evidence-1", "relevance": "high"}),
])
def test_context_and_link_require_matching_identity(routes, method, path, body):
    client, _, _, mapping_service, context_service = routes
    response = client.request(
        method, f"/api/v1/goals/goal-1/{path}", params={"user_id": "other"}, json=body
    )
    assert response.status_code == 403
    mapping_service.create_mapping.assert_not_called()
    context_service.get_context.assert_not_called()
