import os

import pytest

os.environ.setdefault("AUTH_ISSUER", "https://auth.example.test")
os.environ.setdefault(
    "AUTH_JWKS_URL",
    "https://auth.example.test/.well-known/jwks.json",
)
os.environ.setdefault(
    "ALLOWED_ORIGINS",
    "http://localhost:5174,http://127.0.0.1:5174",
)


@pytest.fixture(autouse=True)
def bypass_main_app_authentication_for_integration_tests():
    from app.auth import authorize_request_user
    from app.main import app

    previous = app.dependency_overrides.get(authorize_request_user)
    app.dependency_overrides[authorize_request_user] = lambda: None
    yield
    if previous is None:
        app.dependency_overrides.pop(authorize_request_user, None)
    else:
        app.dependency_overrides[authorize_request_user] = previous
