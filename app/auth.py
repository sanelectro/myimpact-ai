from functools import lru_cache
from json import JSONDecodeError
import re
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import (
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from app.config.settings import get_settings

bearer_scheme = HTTPBearer(auto_error=False)
ADMIN_READABLE_USER_DATA_PATHS = (
    re.compile(r"^/api/v1/goals$"),
    re.compile(r"^/api/v1/goals/[^/]+$"),
    re.compile(r"^/api/v1/goals/[^/]+/(?:evidence|impact)$"),
)


class AuthenticatedUser:
    def __init__(
        self,
        user_id: str,
        email: str,
        role: str | None,
        scopes: set[str],
        name: str | None = None,
        is_platform_admin: bool = False,
    ):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.scopes = scopes
        self.name = name
        self.is_platform_admin = is_platform_admin


@lru_cache
def _get_jwks_client() -> PyJWKClient:
    settings = get_settings()
    return PyJWKClient(settings.auth_jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(
            credentials.credentials
        ).key
    except PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The authentication issuer is temporarily unavailable.",
        ) from exc
    except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        claims = jwt.decode(
            credentials.credentials,
            signing_key,
            algorithms=["RS256"],
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    subject = claims.get("sub")
    email = claims.get("email")
    scope_claim = claims.get("scope", "")
    scopes = set(scope_claim.split()) if isinstance(scope_claim, str) else set()
    if not isinstance(subject, str) or not subject or not isinstance(email, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is missing user identity claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if "myimpact-ai" not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The access token does not grant access to MyImpact AI.",
        )
    name = claims.get("name")
    return AuthenticatedUser(
        subject,
        email,
        claims.get("role"),
        scopes,
        name if isinstance(name, str) else None,
        claims.get("is_platform_admin") is True,
    )


async def authorize_request_user(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    requested_user_ids = list(request.query_params.getlist("user_id"))
    path_user_id = request.path_params.get("user_id")
    if isinstance(path_user_id, str):
        requested_user_ids.append(path_user_id)

    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0]
    if content_type in {"application/x-www-form-urlencoded", "multipart/form-data"}:
        form = await request.form()
        requested_user_ids.extend(
            value
            for value in form.getlist("user_id")
            if isinstance(value, str)
        )
    elif content_type == "application/json":
        try:
            body = await request.json()
        except JSONDecodeError:
            body = None
        if isinstance(body, dict):
            body_user_id = body.get("user_id")
            if isinstance(body_user_id, str):
                requested_user_ids.append(body_user_id)

    admin_read_access = (
        current_user.is_platform_admin
        and request.method == "GET"
        and any(
            path.fullmatch(request.url.path)
            for path in ADMIN_READABLE_USER_DATA_PATHS
        )
    )
    if any(user_id != current_user.user_id for user_id in requested_user_ids) and not admin_read_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The authenticated user cannot access another user's data.",
        )

    requested_email = request.path_params.get("email")
    if isinstance(requested_email, str) and requested_email.casefold() != current_user.email.casefold():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The authenticated user cannot access another user's data.",
        )

    return current_user
