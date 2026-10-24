from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.organization import OrganizationDB
from app.db.models.team import TeamDB
from app.db.models.user import UserDB
from app.db.session import get_db
from app.models.profile import (
    ProfileResponse,
    ProfileRole,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    DirectReportOption,
    DirectReportRoleUpdateRequest,
    ReportingManagerOption,
    TeamOption,
)

router = APIRouter(prefix="/profile", tags=["profile"])

INDIVIDUAL_CONTRIBUTOR_ROLES = {
    ProfileRole.TRAINEE_ENGINEER.value,
    ProfileRole.JUNIOR_ENGINEER.value,
    ProfileRole.SOFTWARE_ENGINEER.value,
    ProfileRole.SENIOR_ENGINEER.value,
    ProfileRole.LEAD_ENGINEER.value,
    ProfileRole.LEAD_ARCHITECT.value,
}
MANAGER_ROLES = {
    ProfileRole.ENGINEERING_MANAGER.value,
    ProfileRole.SENIOR_ENGINEERING_MANAGER.value,
}


def _role_options(role: str) -> set[str]:
    if role in INDIVIDUAL_CONTRIBUTOR_ROLES:
        return MANAGER_ROLES
    if role in MANAGER_ROLES:
        return {ProfileRole.ENGINEERING_DIRECTOR.value}
    return set()


def _direct_report_role_options(manager_role: str | None) -> list[ProfileRole]:
    if manager_role is None:
        return []
    return [
        role
        for role in ProfileRole
        if manager_role in _role_options(role.value)
    ]


def _get_or_create_user(db: Session, current_user: AuthenticatedUser) -> UserDB:
    user = db.get(UserDB, current_user.user_id)
    if user is not None:
        return user

    user = UserDB(
        id=current_user.user_id,
        name=current_user.name or current_user.email.split("@", maxsplit=1)[0],
        email=current_user.email,
        role=current_user.role,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user = db.get(UserDB, current_user.user_id)
        if user is None:
            raise
    return user


def _profile_response(db: Session, user: UserDB) -> ProfileResponse:
    organization = db.get(OrganizationDB, user.organization_id) if user.organization_id else None
    team = db.get(TeamDB, user.team_id) if user.team_id else None
    manager = db.get(UserDB, user.reporting_manager_id) if user.reporting_manager_id else None
    direct_reports = db.scalars(
        select(UserDB)
        .where(UserDB.reporting_manager_id == user.id)
        .order_by(UserDB.name, UserDB.id)
    ).all()
    return ProfileResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        company=organization.name if organization else None,
        organization_id=user.organization_id,
        team=team.name if team else None,
        role=user.role,
        reporting_manager_id=user.reporting_manager_id,
        reporting_manager=(
            ReportingManagerOption(id=manager.id, name=manager.name, role=manager.role)
            if manager is not None and manager.role is not None
            else None
        ),
        direct_reports=[
            DirectReportOption(id=report.id, name=report.name, role=report.role)
            for report in direct_reports
        ],
        direct_report_role_options=_direct_report_role_options(user.role),
    )


def _manager_options(
    db: Session,
    organization_id: str | None,
    role: str | None,
    team_id: str | None = None,
) -> list[ReportingManagerOption]:
    permitted_roles = (
        _role_options(role)
        if role is not None
        else MANAGER_ROLES | {ProfileRole.ENGINEERING_DIRECTOR.value}
    )
    if organization_id is None or not permitted_roles:
        return []
    query = select(UserDB).where(
        UserDB.organization_id == organization_id,
        UserDB.role.in_(permitted_roles),
    )
    if team_id is not None:
        query = query.where(UserDB.team_id == team_id)
    managers = db.scalars(query.order_by(UserDB.name, UserDB.id)).all()
    return [
        ReportingManagerOption(id=manager.id, name=manager.name, role=manager.role)
        for manager in managers
        if manager.role is not None
    ]


@router.get("", response_model=ProfileResponse)
def get_profile(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileResponse:
    return _profile_response(db, _get_or_create_user(db, current_user))


@router.get("/teams", response_model=list[TeamOption])
def get_teams(
    company: Annotated[str, Query(min_length=1, max_length=200)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[TeamOption]:
    profile = db.get(UserDB, current_user.user_id)
    if profile is None or profile.organization_id is None:
        return []
    organization = db.scalar(
        select(OrganizationDB).where(
            OrganizationDB.normalized_name == company.strip().casefold()
        )
    )
    if organization is None or organization.id != profile.organization_id:
        return []
    teams = db.scalars(
        select(TeamDB)
        .where(TeamDB.organization_id == organization.id)
        .order_by(TeamDB.name, TeamDB.id)
    ).all()
    return [TeamOption(id=team.id, name=team.name) for team in teams]


@router.get("/reporting-managers", response_model=list[ReportingManagerOption])
def get_reporting_managers(
    company: Annotated[str, Query(min_length=1, max_length=200)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    role: ProfileRole | None = None,
    team: Annotated[str | None, Query(max_length=200)] = None,
) -> list[ReportingManagerOption]:
    profile = db.get(UserDB, current_user.user_id)
    if profile is None or profile.organization_id is None:
        return []

    organization = db.scalar(
        select(OrganizationDB).where(
            OrganizationDB.normalized_name == company.strip().casefold()
        )
    )
    if organization is None or organization.id != profile.organization_id:
        return []
    team_id = None
    if team is not None and team.strip():
        selected_team = db.scalar(
            select(TeamDB).where(
                TeamDB.organization_id == organization.id,
                TeamDB.normalized_name == " ".join(team.split()).casefold(),
            )
        )
        if selected_team is None:
            return []
        team_id = selected_team.id
    options = _manager_options(
        db, organization.id, role.value if role is not None else None, team_id
    )
    return [option for option in options if option.id != current_user.user_id]


@router.put("", response_model=ProfileUpdateResponse)
def update_profile(
    request: ProfileUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileUpdateResponse:
    user = _get_or_create_user(db, current_user)
    requested_role = request.role.value if request.role is not None else None
    if requested_role != user.role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only your reporting manager can change your role.",
        )
    normalized_company = request.company.casefold()
    organization = db.scalar(
        select(OrganizationDB).where(
            OrganizationDB.normalized_name == normalized_company
        )
    )
    if organization is None:
        organization = OrganizationDB(
            id=str(uuid4()),
            name=request.company,
            normalized_name=normalized_company,
            created_at=datetime.now(UTC),
        )
        db.add(organization)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            user = _get_or_create_user(db, current_user)
            organization = db.scalar(
                select(OrganizationDB).where(
                    OrganizationDB.normalized_name == normalized_company
                )
            )
            if organization is None:
                raise

    team = None
    if request.team is not None:
        normalized_team = request.team.casefold()
        team = db.scalar(
            select(TeamDB).where(
                TeamDB.organization_id == organization.id,
                TeamDB.normalized_name == normalized_team,
            )
        )
        if team is None:
            team = TeamDB(
                id=str(uuid4()),
                organization_id=organization.id,
                name=request.team,
                normalized_name=normalized_team,
                created_at=datetime.now(UTC),
            )
            db.add(team)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                user = _get_or_create_user(db, current_user)
                organization = db.scalar(
                    select(OrganizationDB).where(
                        OrganizationDB.normalized_name == normalized_company
                    )
                )
                if organization is None:
                    raise
                team = db.scalar(
                    select(TeamDB).where(
                        TeamDB.organization_id == organization.id,
                        TeamDB.normalized_name == normalized_team,
                    )
                )
                if team is None:
                    raise

    if (
        user.organization_id != organization.id
        and db.scalar(
            select(UserDB.id).where(UserDB.reporting_manager_id == user.id).limit(1)
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reassign your direct reports before changing companies.",
        )

    permitted_roles = (
        _role_options(request.role.value)
        if request.role is not None
        else MANAGER_ROLES | {ProfileRole.ENGINEERING_DIRECTOR.value}
    )
    if request.reporting_manager_id is not None:
        if request.reporting_manager_id == user.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="You cannot report to yourself.",
            )
        manager = db.get(UserDB, request.reporting_manager_id)
        if (
            manager is None
            or manager.organization_id != organization.id
            or (team is not None and manager.team_id != team.id)
            or manager.role not in permitted_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Choose an eligible reporting manager from the same team."
                    if team is not None
                    else "Choose an eligible reporting manager from the same company."
                ),
            )

    direct_reports = db.scalars(
        select(UserDB).where(UserDB.reporting_manager_id == user.id)
    ).all()
    if any(
        report.organization_id != organization.id
        or report.team_id != (team.id if team is not None else None)
        or request.role is None
        or request.role.value not in _role_options(report.role or "")
        for report in direct_reports
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update your direct reports before changing your company or role.",
        )

    user.organization_id = organization.id
    user.team_id = team.id if team is not None else None
    user.role = request.role.value if request.role is not None else None
    user.reporting_manager_id = request.reporting_manager_id
    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)

    profile = _profile_response(db, user)
    return ProfileUpdateResponse(
        **profile.model_dump(),
        reporting_manager_options=_manager_options(
            db,
            organization.id,
            request.role.value if request.role is not None else None,
            user.team_id,
        ),
    )


@router.patch(
    "/direct-reports/{report_id}/role",
    response_model=DirectReportOption,
)
def update_direct_report_role(
    report_id: str,
    request: DirectReportRoleUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DirectReportOption:
    manager = _get_or_create_user(db, current_user)
    report = db.get(UserDB, report_id)
    if report is None or report.reporting_manager_id != manager.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The employee is not a direct report.",
        )
    if manager.role not in _role_options(request.role.value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You are not eligible to assign this role to your direct report.",
        )

    report_directs = db.scalars(
        select(UserDB).where(UserDB.reporting_manager_id == report.id)
    ).all()
    if any(
        request.role.value not in _role_options(direct.role or "")
        for direct in report_directs
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update this employee's direct reports before changing their role.",
        )

    report.role = request.role.value
    report.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(report)
    return DirectReportOption(id=report.id, name=report.name, role=report.role)
