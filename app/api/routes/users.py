from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserCreate
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


def get_user_service(
    db: Annotated[Session, Depends(get_db)],
) -> UserService:
    return UserService(db)


@router.post(
    "",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_data: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
) -> User:
    user = service.create_user(user_data)
    return User.model_validate(user, from_attributes=True)


@router.get(
    "/email/{email}",
    response_model=User,
)
def get_user_by_email(
    email: str,
    service: Annotated[UserService, Depends(get_user_service)],
) -> User:
    user = service.get_user_by_email(email)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return User.model_validate(user, from_attributes=True)


@router.get(
    "/{user_id}",
    response_model=User,
)
def get_user_by_id(
    user_id: str,
    service: Annotated[UserService, Depends(get_user_service)],
) -> User:
    user = service.get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return User.model_validate(user, from_attributes=True)
