from typing import Any

from fastapi import HTTPException, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


V1_PREFIX = "/api/v1"


def _is_v1_request(request: Request) -> bool:
    return request.url.path == V1_PREFIX or request.url.path.startswith(f"{V1_PREFIX}/")


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details is not None:
        error["details"] = details

    return JSONResponse(
        status_code=status_code,
        content={"error": error},
    )


async def handle_v1_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if not _is_v1_request(request):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    code = f"HTTP_{exc.status_code}"
    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=str(exc.detail),
    )


async def handle_v1_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    if not _is_v1_request(request):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    return _error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=exc.errors(),
    )


async def handle_v1_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not _is_v1_request(request):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )

    return _error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred",
    )
