from app.services.demo_source_mocks import mock_source_response
import base64
import hashlib
import hmac
import json
import logging
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.models.source_connection import SourceConnectionDB


SUPPORTED_PROVIDERS = {"github", "jira"}
OAUTH_STATE_TTL_SECONDS = 600
TOKEN_REFRESH_MARGIN = timedelta(minutes=2)
logger = logging.getLogger(__name__)


class SourceConnectionError(Exception):
    pass


@lru_cache(maxsize=2)
def _read_keychain_secret(service: str, account: str) -> str:
    if sys.platform != "darwin":
        raise SourceConnectionError(
            "Local Keychain source tokens are supported only on macOS."
        )
    try:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(
            "Keychain lookup failed for service=%s account=%s (%s)",
            service,
            account,
            type(exc).__name__,
        )
        raise SourceConnectionError(
            f"Could not read the local Keychain item for {account}."
        ) from exc
    secret = result.stdout.rstrip("\r\n")
    if result.returncode != 0 or not secret:
        logger.warning(
            "Keychain item unavailable for service=%s account=%s (exit=%s)",
            service,
            account,
            result.returncode,
        )
        raise SourceConnectionError(
            f"Local Keychain item {service}/{account} is missing or unavailable."
        )
    return secret


@dataclass(frozen=True)
class LocalSourceConnection:
    external_account_id: str
    external_username: str
    external_base_url: str | None
    jira_email: str | None = None



def _get_demo_source_connection(
    provider: str,
    user_id: str,
) -> tuple[str, LocalSourceConnection] | None:
    settings = get_settings()
    if not settings.source_demo_mocks_enabled:
        return None
    if settings.app_env.casefold() != "development":
        raise SourceConnectionError(
            "Demo source mocks are only allowed when APP_ENV=development."
        )
    if provider not in SUPPORTED_PROVIDERS:
        raise SourceConnectionError("Unsupported evidence source.")

    account = "Demo GitHub workspace" if provider == "github" else "Demo Jira site"
    base_url = "https://github.com" if provider == "github" else None
    return (
        f"myimpact-demo-mock:{provider}:{user_id}",
        LocalSourceConnection(
            external_account_id=f"demo-{provider}",
            external_username=account,
            external_base_url=base_url,
            jira_email=f"{user_id}@myimpact.local" if provider == "jira" else None,
        ),
    )


def _is_demo_mock_token(access_token: str) -> bool:
    if not access_token.startswith("myimpact-demo-mock:"):
        return False
    settings = get_settings()
    if (
        not settings.source_demo_mocks_enabled
        or settings.app_env.casefold() != "development"
    ):
        raise SourceConnectionError(
            "Demo source mocks are only allowed when enabled in development."
        )
    return True


def _get_local_source_connection(
    provider: str,
) -> tuple[str, LocalSourceConnection] | None:
    settings = get_settings()
    if not settings.source_local_tokens_enabled:
        return None
    if settings.app_env.casefold() != "development":
        raise SourceConnectionError(
            "Local source tokens are only allowed when APP_ENV=development."
        )

    def read_token(env_token: str, account: str) -> str:
        if settings.source_local_tokens_from_keychain:
            logger.info(
                "Reading local Keychain credential for provider=%s service=%s account=%s",
                provider,
                settings.source_local_keychain_service,
                account,
            )
            return _read_keychain_secret(
                settings.source_local_keychain_service,
                account,
            )
        logger.info("Reading local environment credential for provider=%s", provider)
        return env_token

    if provider == "github":
        token = read_token(
            settings.github_token,
            settings.source_local_keychain_github_account,
        )
        if not token:
            return None
        return token, LocalSourceConnection(
            external_account_id="local-token",
            external_username="Local GitHub token",
            external_base_url="https://github.com",
        )

    if provider == "jira":
        values = (
            settings.jira_base_url.strip(),
            settings.jira_email.strip(),
            read_token(
                settings.jira_api_token,
                settings.source_local_keychain_jira_account,
            ),
        )
        if not any(values):
            return None
        if not all(values):
            raise SourceConnectionError(
                "Jira local credentials are incomplete. Set JIRA_BASE_URL, "
                "JIRA_EMAIL, and JIRA_API_TOKEN."
            )
        base_url = values[0].rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise SourceConnectionError("JIRA_BASE_URL must use HTTP or HTTPS.")
        return values[2], LocalSourceConnection(
            external_account_id="local-token",
            external_username="Local Jira token",
            external_base_url=base_url,
            jira_email=values[1],
        )

    return None


def _fernet() -> Fernet:
    key = get_settings().source_token_encryption_key
    if not key:
        raise SourceConnectionError(
            "Source integrations are not configured: SOURCE_TOKEN_ENCRYPTION_KEY is missing."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise SourceConnectionError(
            "Source integrations are not configured with a valid token encryption key."
        ) from exc


def _encode_state(payload: dict[str, str | int]) -> str:
    secret = get_settings().source_oauth_state_secret
    if not secret:
        raise SourceConnectionError(
            "Source integrations are not configured: SOURCE_OAUTH_STATE_SECRET is missing."
        )
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256)
    signed = base64.urlsafe_b64encode(signature.digest()).decode("ascii").rstrip("=")
    return f"{encoded}.{signed}"


def _decode_state(state: str, expected_provider: str) -> dict[str, str]:
    secret = get_settings().source_oauth_state_secret
    if not secret or "." not in state:
        raise SourceConnectionError("OAuth state is invalid or expired.")
    encoded, supplied_signature = state.rsplit(".", maxsplit=1)
    expected_signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise SourceConnectionError("OAuth state is invalid or expired.")
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        )
        timestamp = int(payload["t"])
        user_id = payload["u"]
        provider = payload["p"]
        goal_id = payload.get("g", "")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise SourceConnectionError("OAuth state is invalid or expired.") from exc
    now = int(datetime.now(UTC).timestamp())
    if (
        provider != expected_provider
        or not isinstance(user_id, str)
        or not user_id
        or now - timestamp > OAUTH_STATE_TTL_SECONDS
        or timestamp > now + 30
    ):
        raise SourceConnectionError("OAuth state is invalid or expired.")
    return {"user_id": user_id, "goal_id": goal_id}


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> dict | list:
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    data = None
    if body is not None:
        if request_headers.get("Content-Type") == "application/json":
            data = json.dumps(body).encode("utf-8")
        else:
            data = urllib.parse.urlencode(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            if not isinstance(parsed, (dict, list)):
                raise SourceConnectionError("The source returned an invalid response.")
            return parsed
    except urllib.error.HTTPError as exc:
        raise SourceConnectionError(
            f"The source request failed with HTTP {exc.code}."
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SourceConnectionError("The source could not be reached.") from exc
    except json.JSONDecodeError as exc:
        raise SourceConnectionError("The source returned invalid JSON.") from exc


def get_authorization_url(provider: str, user_id: str, goal_id: str) -> str:
    if provider not in SUPPORTED_PROVIDERS:
        raise SourceConnectionError("Unsupported evidence source.")
    _fernet()
    settings = get_settings()
    state = _encode_state(
        {
            "u": user_id,
            "p": provider,
            "g": goal_id,
            "t": int(datetime.now(UTC).timestamp()),
            "n": secrets.token_urlsafe(16),
        }
    )
    if provider == "github":
        if not all(
            (
                settings.github_app_client_id,
                settings.github_app_callback_url,
                settings.github_app_client_secret,
            )
        ):
            raise SourceConnectionError(
                "GitHub App OAuth is not configured. Set the GitHub App client ID, "
                "client secret, and callback URL."
            )
        query = urllib.parse.urlencode(
            {
                "client_id": settings.github_app_client_id,
                "redirect_uri": settings.github_app_callback_url,
                "state": state,
            }
        )
        return f"https://github.com/login/oauth/authorize?{query}"

    if not all(
        (
            settings.atlassian_client_id,
            settings.atlassian_client_secret,
            settings.atlassian_callback_url,
        )
    ):
        raise SourceConnectionError(
            "Atlassian OAuth is not configured. Set the client ID, client secret, "
            "and callback URL."
        )
    query = urllib.parse.urlencode(
        {
            "audience": "api.atlassian.com",
            "client_id": settings.atlassian_client_id,
            "scope": "read:jira-user read:jira-work offline_access",
            "redirect_uri": settings.atlassian_callback_url,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
        }
    )
    return f"https://auth.atlassian.com/authorize?{query}"


def complete_oauth(
    session: Session,
    provider: str,
    code: str,
    state: str,
) -> tuple[str, str]:
    if provider not in SUPPORTED_PROVIDERS:
        raise SourceConnectionError("Unsupported evidence source.")
    state_data = _decode_state(state, provider)
    settings = get_settings()
    if provider == "github":
        token_data = _request_json(
            "https://github.com/login/oauth/access_token",
            method="POST",
            body={
                "client_id": settings.github_app_client_id,
                "client_secret": settings.github_app_client_secret,
                "code": code,
                "redirect_uri": settings.github_app_callback_url,
            },
        )
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise SourceConnectionError("GitHub did not authorize this connection.")
        account = _request_json(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        account_id = account.get("id")
        username = account.get("login")
        refresh_token = token_data.get("refresh_token")
        expires_at = _token_expiry(token_data)
        base_url = "https://github.com"
    else:
        token_data = _request_json(
            "https://auth.atlassian.com/oauth/token",
            method="POST",
            headers={"Content-Type": "application/json"},
            body={
                "grant_type": "authorization_code",
                "client_id": settings.atlassian_client_id,
                "client_secret": settings.atlassian_client_secret,
                "code": code,
                "redirect_uri": settings.atlassian_callback_url,
            },
        )
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise SourceConnectionError("Atlassian did not authorize this connection.")
        resources = _request_json(
            "https://api.atlassian.com/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if not isinstance(resources, list) or not resources:
            raise SourceConnectionError("No Jira site is accessible to this account.")
        if len(resources) > 1:
            raise SourceConnectionError(
                "More than one Jira site is available to this account. Configure "
                "the Atlassian authorization so only the intended site is accessible."
            )
        jira_site = resources[0]
        account_id = jira_site.get("id")
        base_url = jira_site.get("url")
        account = _request_json(
            f"https://api.atlassian.com/ex/jira/{account_id}/rest/api/3/myself",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        username = account.get("displayName") or account.get("emailAddress")
        expires_at = _token_expiry(token_data)

    if not isinstance(account_id, (str, int)) or not isinstance(username, str) or not username:
        raise SourceConnectionError("The provider returned an incomplete account profile.")

    connection = (
        session.query(SourceConnectionDB)
        .filter_by(user_id=state_data["user_id"], provider=provider)
        .one_or_none()
    )
    now = datetime.now(UTC)
    values = {
        "external_account_id": str(account_id),
        "external_username": username,
        "external_base_url": base_url if isinstance(base_url, str) else None,
        "access_token_ciphertext": _fernet().encrypt(access_token.encode("utf-8")).decode("ascii"),
        "refresh_token_ciphertext": (
            _fernet().encrypt(refresh_token.encode("utf-8")).decode("ascii")
            if isinstance(refresh_token, str) and refresh_token
            else None
        ),
        "expires_at": expires_at,
        "updated_at": now,
    }
    if connection is None:
        connection = SourceConnectionDB(
            id=str(uuid4()),
            user_id=state_data["user_id"],
            provider=provider,
            created_at=now,
            **values,
        )
        session.add(connection)
    else:
        for key, value in values.items():
            setattr(connection, key, value)
    session.commit()
    return state_data["user_id"], state_data["goal_id"]


def _token_expiry(token_data: dict) -> datetime | None:
    expires_in = token_data.get("expires_in")
    if isinstance(expires_in, (int, float)):
        return datetime.now(UTC) + timedelta(seconds=expires_in)
    return None


def get_connection_status(session: Session, user_id: str) -> list[dict[str, str | bool]]:
    if get_settings().source_demo_mocks_enabled:
        return [
            {
                "provider": provider,
                "connected": True,
                "account": _get_demo_source_connection(provider, user_id)[1].external_username,
                "managed_locally": True,
            }
            for provider in sorted(SUPPORTED_PROVIDERS)
        ]
    connections = (
        session.query(SourceConnectionDB)
        .filter_by(user_id=user_id)
        .order_by(SourceConnectionDB.provider)
        .all()
    )
    by_provider = {item.provider: item for item in connections}
    status = []
    for provider in sorted(SUPPORTED_PROVIDERS):
        connection = by_provider.get(provider)
        if connection is not None:
            status.append(
                {
                    "provider": provider,
                    "connected": True,
                    "account": connection.external_username,
                    "managed_locally": False,
                }
            )
            continue
        local_connection = _get_local_source_connection(provider)
        status.append(
            {
                "provider": provider,
                "connected": local_connection is not None,
                "account": (
                    local_connection[1].external_username if local_connection else ""
                ),
                "managed_locally": local_connection is not None,
            }
        )
    return status


def disconnect_source(session: Session, user_id: str, provider: str) -> None:
    if provider not in SUPPORTED_PROVIDERS:
        raise SourceConnectionError("Unsupported evidence source.")
    connection = (
        session.query(SourceConnectionDB)
        .filter_by(user_id=user_id, provider=provider)
        .one_or_none()
    )
    if connection is not None:
        session.delete(connection)
        session.commit()


def get_access_token(
    session: Session,
    user_id: str,
    provider: str,
) -> tuple[str, SourceConnectionDB | LocalSourceConnection]:
    demo_connection = _get_demo_source_connection(provider, user_id)
    if demo_connection is not None:
        logger.info("Using demo mock source for provider=%s", provider)
        return demo_connection

    connection = (
        session.query(SourceConnectionDB)
        .filter_by(user_id=user_id, provider=provider)
        .one_or_none()
    )
    if connection is None:
        local_connection = _get_local_source_connection(provider)
        if local_connection is None:
            raise SourceConnectionError(f"Connect your {provider.title()} account first.")
        source = (
            "Keychain"
            if get_settings().source_local_tokens_from_keychain
            else "environment"
        )
        logger.info("Using local %s credential for provider=%s", source, provider)
        return local_connection
    logger.info("Using saved connection for provider=%s", provider)
    try:
        access_token = _fernet().decrypt(
            connection.access_token_ciphertext.encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise SourceConnectionError(
            f"Your {provider.title()} connection could not be decrypted. Reconnect it."
        ) from exc

    if connection.expires_at and connection.expires_at <= datetime.now(UTC) + TOKEN_REFRESH_MARGIN:
        access_token = _refresh_access_token(session, connection)
    return access_token, connection


def _refresh_access_token(session: Session, connection: SourceConnectionDB) -> str:
    if not connection.refresh_token_ciphertext:
        raise SourceConnectionError(
            f"Your {connection.provider.title()} authorization expired. Reconnect it."
        )
    try:
        refresh_token = _fernet().decrypt(
            connection.refresh_token_ciphertext.encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise SourceConnectionError(
            f"Your {connection.provider.title()} connection could not be decrypted. Reconnect it."
        ) from exc
    settings = get_settings()
    if connection.provider == "github":
        token_url = "https://github.com/login/oauth/access_token"
        body = {
            "client_id": settings.github_app_client_id,
            "client_secret": settings.github_app_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    else:
        token_url = "https://auth.atlassian.com/oauth/token"
        body = {
            "client_id": settings.atlassian_client_id,
            "client_secret": settings.atlassian_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    token_data = _request_json(
        token_url,
        method="POST",
        headers={"Content-Type": "application/json"} if connection.provider == "jira" else None,
        body=body,
    )
    access_token = token_data.get("access_token")
    next_refresh_token = token_data.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise SourceConnectionError(
            f"{connection.provider.title()} could not refresh authorization. Reconnect it."
        )
    fernet = _fernet()
    connection.access_token_ciphertext = fernet.encrypt(access_token.encode()).decode("ascii")
    if isinstance(next_refresh_token, str) and next_refresh_token:
        connection.refresh_token_ciphertext = fernet.encrypt(
            next_refresh_token.encode()
        ).decode("ascii")
    connection.expires_at = _token_expiry(token_data)
    connection.updated_at = datetime.now(UTC)
    session.commit()
    return access_token


def source_api_get(
    url: str,
    access_token: str,
    provider: str,
    *,
    params: dict[str, str] | None = None,
    jira_email: str | None = None,
) -> dict | list:
    if _is_demo_mock_token(access_token):
        return mock_source_response(
            "GET",
            url,
            access_token,
            provider,
            params=params,
        )
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    if provider == "jira" and jira_email:
        credentials = base64.b64encode(
            f"{jira_email}:{access_token}".encode("utf-8")
        ).decode("ascii")
        authorization = f"Basic {credentials}"
    else:
        authorization = f"Bearer {access_token}"
    headers = {"Authorization": authorization}
    if provider == "github":
        headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
    try:
        return _request_json(url, headers=headers)
    except SourceConnectionError as exc:
        provider_name = "GitHub" if provider == "github" else provider.title()
        request_path = urllib.parse.urlsplit(url).path
        logger.warning(
            "%s source request failed for path=%s: %s",
            provider_name,
            request_path,
            exc,
        )
        raise


def source_api_post(
    url: str,
    access_token: str,
    body: dict,
    *,
    jira_email: str | None = None,
) -> dict | list:
    if _is_demo_mock_token(access_token):
        return mock_source_response(
            "POST",
            url,
            access_token,
            "jira",
            body=body,
        )
    if jira_email:
        credentials = base64.b64encode(
            f"{jira_email}:{access_token}".encode("utf-8")
        ).decode("ascii")
        authorization = f"Basic {credentials}"
    else:
        authorization = f"Bearer {access_token}"
    try:
        return _request_json(
            url,
            method="POST",
            headers={
                "Authorization": authorization,
                "Content-Type": "application/json",
            },
            body=body,
        )
    except SourceConnectionError as exc:
        request_path = urllib.parse.urlsplit(url).path
        logger.warning("Jira source request failed for path=%s: %s", request_path, exc)
        raise
