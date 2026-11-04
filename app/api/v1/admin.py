from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.assessment_category import AssessmentCategoryDB
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


class AssessmentCategoryCriterionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    definition: dict


class AssessmentCategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Category name must not be blank.")
        return normalized


class AssessmentCategoryResponse(BaseModel):
    id: str
    name: str
    description: str | None
    criteria: list[dict]
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _require_platform_admin(current_user: AuthenticatedUser) -> None:
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access is required.",
        )


@router.get("/users", response_model=list[AdminUserResponse])
def get_all_users(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AdminUserResponse]:
    _require_platform_admin(current_user)

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
    _require_platform_admin(current_user)

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
    _require_platform_admin(current_user)

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


@router.get(
    "/assessment-categories",
    response_model=list[AssessmentCategoryResponse],
)
def list_assessment_categories(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AssessmentCategoryResponse]:
    _require_platform_admin(current_user)
    categories = db.scalars(
        select(AssessmentCategoryDB).order_by(
            AssessmentCategoryDB.name, AssessmentCategoryDB.id
        )
    ).all()
    return [
        AssessmentCategoryResponse.model_validate(category, from_attributes=True)
        for category in categories
    ]


@router.post(
    "/assessment-categories",
    response_model=AssessmentCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment_category(
    request: AssessmentCategoryCreateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AssessmentCategoryResponse:
    _require_platform_admin(current_user)
    now = datetime.now(UTC)
    category = AssessmentCategoryDB(
        id=str(uuid4()),
        name=request.name,
        normalized_name=request.name.casefold(),
        description=request.description,
        criteria=[],
        created_by_user_id=current_user.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An assessment category with this name already exists.",
        ) from error
    db.refresh(category)
    return AssessmentCategoryResponse.model_validate(category, from_attributes=True)


@router.post(
    "/assessment-categories/{category_id}/criteria",
    response_model=AssessmentCategoryResponse,
)
def add_assessment_category_criterion(
    category_id: str,
    request: AssessmentCategoryCriterionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AssessmentCategoryResponse:
    _require_platform_admin(current_user)
    category = db.get(AssessmentCategoryDB, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment category not found.",
        )
    from app.models.goal_criteria import GoalCriterionDefinition

    try:
        definition = GoalCriterionDefinition.model_validate(request.definition)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Criterion definition is invalid.",
        ) from error
    criterion = {
        "id": str(uuid4()),
        "title": request.title,
        "definition": definition.model_dump(mode="json"),
        "created_at": datetime.now(UTC).isoformat(),
        "created_by_user_id": current_user.user_id,
    }
    category.criteria = [*category.criteria, criterion]
    category.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(category)
    return AssessmentCategoryResponse.model_validate(category, from_attributes=True)
