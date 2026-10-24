import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.source_connection import SourceConnectionDB
from app.db.models.user import UserDB
from app.services import source_connections


def _settings():
    return SimpleNamespace(
        source_token_encryption_key=Fernet.generate_key().decode("ascii"),
        source_oauth_state_secret="state-secret-for-tests",
        app_env="development",
        source_demo_mocks_enabled=False,
        source_local_tokens_enabled=False,
        source_local_tokens_from_keychain=False,
        source_local_keychain_service="MyImpact-local",
        source_local_keychain_github_account="GITHUB_TOKEN",
        source_local_keychain_jira_account="JIRA_API_TOKEN",
        github_token="",
        jira_base_url="",
        jira_email="",
        jira_api_token="",
        github_app_client_id="github-client",
        github_app_client_secret="github-secret",
        github_app_callback_url="https://myimpact.test/callback/github",
        atlassian_client_id="jira-client",
        atlassian_client_secret="jira-secret",
        atlassian_callback_url="https://myimpact.test/callback/jira",
        source_integrations_web_url="https://myimpact.test",
    )


def test_oauth_state_is_signed_and_bound_to_provider_and_user(monkeypatch):
    monkeypatch.setattr(source_connections, "get_settings", _settings)
    state = source_connections._encode_state(
        {"u": "user-1", "p": "github", "g": "goal-1", "t": int(datetime.now(UTC).timestamp())}
    )

    assert source_connections._decode_state(state, "github") == {
        "user_id": "user-1",
        "goal_id": "goal-1",
    }
    with pytest.raises(source_connections.SourceConnectionError):
        source_connections._decode_state(f"{state}tampered", "github")
    with pytest.raises(source_connections.SourceConnectionError):
        source_connections._decode_state(state, "jira")


def test_github_connect_url_uses_configured_app_and_signed_goal_state(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)

    authorization_url = source_connections.get_authorization_url(
        "github",
        "user-1",
        "goal-1",
    )
    query = parse_qs(urlparse(authorization_url).query)

    assert urlparse(authorization_url).netloc == "github.com"
    assert query["client_id"] == ["github-client"]
    assert query["redirect_uri"] == ["https://myimpact.test/callback/github"]
    assert source_connections._decode_state(query["state"][0], "github") == {
        "user_id": "user-1",
        "goal_id": "goal-1",
    }


def test_oauth_callback_persists_encrypted_user_scoped_connection(monkeypatch):
    settings = _settings()
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[UserDB.__table__, SourceConnectionDB.__table__],
    )
    session = Session(engine)
    now = datetime.now(UTC)
    session.add(
        UserDB(
            id="user-1",
            name="Test User",
            email="user@example.test",
            role=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()

    monkeypatch.setattr(
        source_connections,
        "_request_json",
        lambda url, **kwargs: (
            {"access_token": "provider-access-token"}
            if "login/oauth/access_token" in url
            else {"id": 42, "login": "test-user"}
        ),
    )
    state = source_connections._encode_state(
        {"u": "user-1", "p": "github", "g": "goal-1", "t": int(datetime.now(UTC).timestamp())}
    )

    user_id, goal_id = source_connections.complete_oauth(
        session,
        "github",
        "one-time-code",
        state,
    )
    connection = session.query(SourceConnectionDB).one()
    encrypted_token = connection.access_token_ciphertext

    assert (user_id, goal_id) == ("user-1", "goal-1")
    assert connection.external_username == "test-user"
    assert encrypted_token != "provider-access-token"
    assert source_connections._fernet().decrypt(encrypted_token.encode()).decode() == "provider-access-token"

    session.close()
    engine.dispose()


def test_local_tokens_are_available_only_when_explicitly_enabled_for_development(
    monkeypatch,
):
    settings = _settings()
    settings.app_env = "development"
    settings.source_local_tokens_enabled = True
    settings.github_token = "local-github-token"
    settings.jira_base_url = "https://example.atlassian.net"
    settings.jira_email = "user@example.test"
    settings.jira_api_token = "local-jira-token"
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)

    github_token, github_connection = source_connections._get_local_source_connection(
        "github"
    )
    jira_token, jira_connection = source_connections._get_local_source_connection(
        "jira"
    )

    assert github_token == "local-github-token"
    assert github_connection.external_username == "Local GitHub token"
    assert jira_token == "local-jira-token"
    assert jira_connection.external_base_url == "https://example.atlassian.net"
    assert jira_connection.jira_email == "user@example.test"

    settings.app_env = "production"
    with pytest.raises(source_connections.SourceConnectionError):
        source_connections._get_local_source_connection("github")


def test_local_jira_api_uses_basic_auth(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        source_connections,
        "_request_json",
        lambda url, **kwargs: captured.update(kwargs) or {},
    )

    source_connections.source_api_get(
        "https://example.atlassian.net/rest/api/3/myself",
        "local-jira-token",
        "jira",
        jira_email="user@example.test",
    )

    assert captured["headers"]["Authorization"].startswith("Basic ")


def test_demo_mock_sources_return_user_scoped_github_and_jira_records(monkeypatch):
    settings = _settings()
    settings.source_demo_mocks_enabled = True
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)

    github_token, _ = source_connections.get_access_token(None, "user-3", "github")
    jira_token, jira_connection = source_connections.get_access_token(
        None, "user-3", "jira"
    )
    profile = source_connections.source_api_get(
        "https://api.github.com/user",
        github_token,
        "github",
    )
    commits = source_connections.source_api_get(
        "https://api.github.com/search/commits",
        github_token,
        "github",
        params={"q": "author:demo-trainee-engineer author-date:2026-10-01..2026-10-23"},
    )
    issue = source_connections.source_api_get(
        "https://api.atlassian.com/ex/jira/demo-jira/rest/api/3/issue/DEMO-103",
        jira_token,
        "jira",
    )
    search = source_connections.source_api_post(
        "https://api.atlassian.com/ex/jira/demo-jira/rest/api/3/search/jql",
        jira_token,
        {"jql": "assignee = currentUser()"},
    )

    assert profile["login"] == "demo-trainee-engineer"
    assert len(commits["items"]) == 1
    assert commits["items"][0]["commit"]["message"].startswith("DEMO-103:")
    assert issue["fields"]["status"]["statusCategory"]["key"] == "done"
    assert [item["key"] for item in search["issues"]] == ["DEMO-103"]
    assert jira_connection.external_base_url is None


def test_demo_mock_requests_are_rejected_when_disabled_or_outside_development(
    monkeypatch,
):
    settings = _settings()
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)

    with pytest.raises(source_connections.SourceConnectionError):
        source_connections.source_api_get(
            "https://api.github.com/user",
            "myimpact-demo-mock:github:user-3",
            "github",
        )

    settings.source_demo_mocks_enabled = True
    settings.app_env = "production"
    with pytest.raises(source_connections.SourceConnectionError):
        source_connections.source_api_get(
            "https://api.github.com/user",
            "myimpact-demo-mock:github:user-3",
            "github",
        )


def test_connection_status_marks_local_token_as_locally_managed(monkeypatch):
    settings = _settings()
    settings.app_env = "development"
    settings.source_local_tokens_enabled = True
    settings.github_token = "local-github-token"
    settings.jira_base_url = ""
    settings.jira_email = ""
    settings.jira_api_token = ""
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[UserDB.__table__, SourceConnectionDB.__table__],
    )
    session = Session(engine)

    statuses = source_connections.get_connection_status(session, "user-1")

    assert next(item for item in statuses if item["provider"] == "github") == {
        "provider": "github",
        "connected": True,
        "account": "Local GitHub token",
        "managed_locally": True,
    }
    assert next(item for item in statuses if item["provider"] == "jira") == {
        "provider": "jira",
        "connected": False,
        "account": "",
        "managed_locally": False,
    }

    session.close()
    engine.dispose()


def test_local_tokens_can_be_read_from_macos_keychain(monkeypatch, caplog):
    settings = _settings()
    settings.source_local_tokens_enabled = True
    settings.source_local_tokens_from_keychain = True
    settings.jira_base_url = "https://example.atlassian.net"
    settings.jira_email = "user@example.test"
    monkeypatch.setattr(source_connections, "get_settings", lambda: settings)
    keychain_accounts = []

    def fake_read_secret(service, account):
        keychain_accounts.append((service, account))
        return f"{account}-value"

    monkeypatch.setattr(source_connections, "_read_keychain_secret", fake_read_secret)

    with caplog.at_level(logging.INFO):
        github_token, _ = source_connections._get_local_source_connection("github")
        jira_token, _ = source_connections._get_local_source_connection("jira")

    assert github_token == "GITHUB_TOKEN-value"
    assert jira_token == "JIRA_API_TOKEN-value"
    assert keychain_accounts == [
        ("MyImpact-local", "GITHUB_TOKEN"),
        ("MyImpact-local", "JIRA_API_TOKEN"),
    ]
    assert "provider=github" in caplog.text
    assert "provider=jira" in caplog.text
    assert "GITHUB_TOKEN-value" not in caplog.text
    assert "JIRA_API_TOKEN-value" not in caplog.text


def test_keychain_reader_reports_missing_item_without_echoing_output(monkeypatch):
    monkeypatch.setattr(source_connections.sys, "platform", "darwin")
    monkeypatch.setattr(
        source_connections.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=44, stdout="", stderr="missing"),
    )
    source_connections._read_keychain_secret.cache_clear()

    with pytest.raises(
        source_connections.SourceConnectionError,
        match="MyImpact-local/GITHUB_TOKEN is missing or unavailable",
    ):
        source_connections._read_keychain_secret("MyImpact-local", "GITHUB_TOKEN")

    source_connections._read_keychain_secret.cache_clear()


def test_source_request_logs_provider_and_error_without_logging_token(
    monkeypatch,
    caplog,
):
    def fail_request(*args, **kwargs):
        raise source_connections.SourceConnectionError(
            "The source request failed with HTTP 401."
        )

    monkeypatch.setattr(source_connections, "_request_json", fail_request)

    with pytest.raises(source_connections.SourceConnectionError):
        source_connections.source_api_get(
            "https://api.github.com/user",
            "do-not-log-this-token",
            "github",
        )

    assert "GitHub source request failed" in caplog.text
    assert "HTTP 401" in caplog.text
    assert "do-not-log-this-token" not in caplog.text
