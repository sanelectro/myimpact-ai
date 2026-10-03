from fastapi.testclient import TestClient

from app.main import app as main_app


client = TestClient(main_app)


EXPECTED_API = {
    "GET": {
        "/api/v1",
        "/api/v1/goals",
        "/api/v1/goals/{goal_id}",
        "/api/v1/knowledge/documents",
        "/api/v1/knowledge/documents/{document_id}",
        "/api/v1/knowledge/documents/{document_id}/expectations",
        "/api/v1/goals/{goal_id}/evidence",
        "/api/v1/goals/{goal_id}/impact",
        "/api/v1/goals/{goal_id}/insight",
        "/api/v1/goals/{goal_id}/report",
    },
    "POST": {
        "/api/v1/goals",
        "/api/v1/knowledge/documents",
        "/api/v1/knowledge/documents/{document_id}/reprocess",
        "/api/v1/knowledge/retrieve",
        "/api/v1/goals/{goal_id}/impact/analyze",
        "/api/v1/chat",
    },
    "PUT": {
        "/api/v1/goals/{goal_id}",
    },
    "DELETE": {
        "/api/v1/goals/{goal_id}",
    },
}


def _method_paths() -> dict[str, set[str]]:
    schema = main_app.openapi()
    paths: dict[str, set[str]] = {method: set() for method in EXPECTED_API}
    for path, operations in schema["paths"].items():
        for method in operations:
            method_upper = method.upper()
            if method_upper in paths:
                paths[method_upper].add(path)
    return paths


def test_m5_product_api_surface_is_mounted():
    actual = _method_paths()

    for method, expected_paths in EXPECTED_API.items():
        missing = expected_paths - actual[method]
        assert not missing, f"Missing {method} API routes: {sorted(missing)}"


def test_api_v1_root_is_available():
    response = client.get("/api/v1")

    assert response.status_code == 200
    body = response.json()
    assert "version" in body


def test_unknown_v1_route_uses_standard_error_contract():
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "HTTP_404"
    assert "message" in body["error"]
    assert "details" in body["error"]
    assert isinstance(body["error"]["details"], list)


def test_chat_validation_uses_standard_error_contract():
    response = client.post(
        "/api/v1/chat?user_id=user-1",
        json={"message": "   "},
    )

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], list)
