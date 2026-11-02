import json
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError

from app.services import source_connections


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_http_error_categories_are_safe_and_non_retryable_errors_do_not_retry():
    permission_error = source_connections._source_http_error(403, None)

    assert permission_error.category == source_connections.SourceErrorCategory.PERMISSION_DENIED
    assert permission_error.retryable is False
    assert "403" not in str(permission_error)


def test_safe_source_requests_retry_transient_failures_with_a_bound(
    monkeypatch,
):
    attempts = {"count": 0}
    sleeps = []

    def request(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise HTTPError(
                "https://api.github.com/test",
                503,
                "temporary",
                {},
                BytesIO(b""),
            )
        return _Response({"ok": True})

    monkeypatch.setattr(source_connections.urllib.request, "urlopen", request)
    monkeypatch.setattr(source_connections, "sleep", sleeps.append)

    result = source_connections._request_json(
        "https://api.github.com/test",
        retry_safe=True,
    )

    assert result == {"ok": True}
    assert attempts["count"] == 3
    assert sleeps == [1.0, 2.0]


def test_rate_limit_retry_after_is_capped():
    error = source_connections._source_http_error(429, 120)

    assert error.category == source_connections.SourceErrorCategory.RATE_LIMITED
    assert error.retryable is True
    assert error.retry_after_seconds == 120


def test_development_demo_sources_return_persona_scoped_results(monkeypatch):
    settings = SimpleNamespace(
        source_demo_mocks_enabled=True,
        app_env="development",
    )
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)

    github_token, github_connection = source_connections.get_access_token(
        None, "user-3", "github"
    )
    jira_token, jira_connection = source_connections.get_access_token(
        None, "user-3", "jira"
    )

    assert github_connection.external_username == "Demo GitHub workspace"
    assert jira_connection.external_username == "Demo Jira site"
    github_result = source_connections.source_api_get(
        "https://api.github.com/search/commits",
        github_token,
        "github",
        params={"q": "author-date:2026-01-01..2026-12-31"},
    )
    jira_result = source_connections.source_api_post(
        "https://demo.atlassian.net/rest/api/3/search/jql",
        jira_token,
        {"jql": "project = DEMO"},
    )

    assert len(github_result["items"]) == 1
    assert len(jira_result["issues"]) == 1


def test_development_demo_sources_distinguish_bounded_no_results(monkeypatch):
    settings = SimpleNamespace(
        source_demo_mocks_enabled=True,
        app_env="development",
    )
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)

    token, _ = source_connections.get_access_token(None, "user-3", "github")
    result = source_connections.source_api_get(
        "https://api.github.com/search/commits",
        token,
        "github",
        params={"q": "author-date:2025-01-01..2025-12-31"},
    )

    assert result == {"items": []}
