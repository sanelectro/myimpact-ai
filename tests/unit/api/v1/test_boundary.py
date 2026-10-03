from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_v1_boundary_is_mounted() -> None:
    response = client.get("/api/v1")

    assert response.status_code == 200
    assert response.json() == {
        "name": "MyImpact AI API",
        "version": "v1",
        "status": "available",
    }


def test_v1_unknown_route_uses_common_error_contract() -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"


def test_v1_validation_error_uses_common_contract() -> None:
    router = APIRouter(prefix="/api/v1/test-contract")

    @router.get("/validation")
    def validation(value: int) -> dict[str, int]:
        return {"value": value}

    app.include_router(router)

    response = client.get("/api/v1/test-contract/validation", params={"value": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed"
    assert body["error"]["details"]


def test_v1_http_exception_uses_common_contract() -> None:
    router = APIRouter(prefix="/api/v1/test-contract")

    @router.get("/not-found")
    def not_found() -> None:
        raise HTTPException(status_code=404, detail="Thing not found")

    app.include_router(router)

    response = client.get("/api/v1/test-contract/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "HTTP_404",
            "message": "Thing not found",
        }
    }
