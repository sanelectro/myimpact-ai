from fastapi import HTTPException, status

from app.exceptions.user import UserAlreadyExistsError


def raise_user_conflict(exc: UserAlreadyExistsError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exc),
    )
