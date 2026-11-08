from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.goal_hierarchy import get_goal_hierarchy_service
from app.auth import AuthenticatedUser, authorize_request_user, get_current_user
from app.main import app


OPERATIONS = [
    ("GET", "hierarchy", None),
    ("GET", "children", None),
    ("GET", "relationship-history", None),
    ("PUT", "parent", {"parent_goal_id": "parent", "expected_revision": 0}),
    ("DELETE", "parent", {"expected_revision": 0}),
]


@pytest.fixture
def routes():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides.pop(authorize_request_user, None)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        "owner", "owner@example.test", None, {"myimpact-ai"}
    )
    service = MagicMock()
    app.dependency_overrides[get_goal_hierarchy_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.parametrize(("method", "operation", "body"), OPERATIONS)
def test_spoofed_identity_cannot_call_hierarchy(routes, method, operation, body):
    client, service = routes
    response = client.request(
        method, f"/api/v1/goals/goal-1/{operation}",
        params={"user_id": "other"}, json=body,
    )
    assert response.status_code == 403
    service.assert_not_called()
    service.set_parent.assert_not_called()
    service.hierarchy.assert_not_called()
    service.children.assert_not_called()
    service.history.assert_not_called()


@pytest.mark.parametrize(("method", "operation", "body"), OPERATIONS)
def test_hierarchy_requires_authentication(routes, method, operation, body):
    client, service = routes
    app.dependency_overrides.pop(get_current_user)
    response = client.request(
        method, f"/api/v1/goals/goal-1/{operation}",
        params={"user_id": "owner"}, json=body,
    )
    assert response.status_code == 401
    service.set_parent.assert_not_called()
    service.hierarchy.assert_not_called()
    service.children.assert_not_called()
    service.history.assert_not_called()
