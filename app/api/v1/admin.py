from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.organization import OrganizationDB
from app.db.models.user import UserDB
from app.db.models.user_invitation import UserInvitationDB
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserResponse(BaseModel):
    id: str
    name: str
    email: str
    company: str | None
    role: str | None
    is_active: bool
    invitation_pending: bool


class AdminCompanyResponse(BaseModel):
    id: str
    name: str
    user_count: int
    created_at: datetime


class AdminCompanyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Company name must not be blank.")
        return normalized


@router.get("/users", response_model=list[AdminUserResponse])
def get_all_users(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AdminUserResponse]:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )

    invitation_pending = exists(
        select(1).where(
            UserInvitationDB.user_id == UserDB.id,
            UserInvitationDB.consumed_at.is_(None),
        )
    )
    users = db.execute(
        select(UserDB, OrganizationDB.name, invitation_pending.label("invitation_pending"))
        .outerjoin(OrganizationDB, UserDB.organization_id == OrganizationDB.id)
        .where(UserDB.is_platform_admin.is_(False))
        .order_by(func.coalesce(OrganizationDB.name, ""), UserDB.name, UserDB.id)
    ).all()
    return [
        AdminUserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            company=company,
            role=user.role,
            is_active=user.is_active,
            invitation_pending=pending,
        )
        for user, company, pending in users
    ]


@router.get("/companies", response_model=list[AdminCompanyResponse])
def get_all_companies(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AdminCompanyResponse]:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )

    companies = db.execute(
        select(OrganizationDB, func.count(UserDB.id).label("user_count"))
        .outerjoin(UserDB, UserDB.organization_id == OrganizationDB.id)
        .group_by(OrganizationDB.id)
        .order_by(OrganizationDB.name, OrganizationDB.id)
    ).all()
    return [
        AdminCompanyResponse(
            id=company.id,
            name=company.name,
            user_count=user_count,
            created_at=company.created_at,
        )
        for company, user_count in companies
    ]


@router.patch(
    "/companies/{company_id}",
    response_model=AdminCompanyResponse,
)
def update_company(
    company_id: str,
    request: AdminCompanyUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminCompanyResponse:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )

    company = db.get(OrganizationDB, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    normalized_name = request.name.casefold()
    duplicate = db.scalar(
        select(OrganizationDB.id).where(
            OrganizationDB.normalized_name == normalized_name,
            OrganizationDB.id != company_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this name already exists.",
        )

    company.name = request.name
    company.normalized_name = normalized_name
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this name already exists.",
        ) from error

    user_count = db.scalar(
        select(func.count(UserDB.id)).where(UserDB.organization_id == company.id)
    )
    return AdminCompanyResponse(
        id=company.id,
        name=company.name,
        user_count=user_count or 0,
        created_at=company.created_at,
    )
