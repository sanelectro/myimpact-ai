from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.organization_role import (
    OrganizationRoleAuditEventDB,
    OrganizationRoleCompetencyDB,
    OrganizationRoleDB,
    OrganizationRoleGoalDB,
    OrganizationRoleResponsibilityDB,
)
from app.db.models.user import UserDB
from app.db.session import get_db
from app.models.profile import ProfileRole
from app.models.role_catalog import (
    CompanyRoleHistoryResponse,
    CompanyRoleResponse,
    CompanyRoleWriteRequest,
    RoleCompetencyResponse,
    RoleGoalResponse,
    RoleResponsibilityResponse,
)

router = APIRouter(prefix="/role-catalog", tags=["role-catalog"])

ROLE_CATALOG_MANAGER_ROLES = {
    ProfileRole.ENGINEERING_MANAGER.value,
    ProfileRole.SENIOR_ENGINEERING_MANAGER.value,
    ProfileRole.ENGINEERING_DIRECTOR.value,
}


def _manager_for_company(
    current_user: AuthenticatedUser,
    db: Session,
) -> UserDB:
    manager = db.get(UserDB, current_user.user_id)
    if (
        manager is None
        or not manager.is_active
        or manager.organization_id is None
        or manager.role not in ROLE_CATALOG_MANAGER_ROLES
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company role management is available to Engineering Managers and above.",
        )
    return manager


def _load_role(db: Session, organization_id: str, role_id: str) -> OrganizationRoleDB:
    role = db.scalar(
        select(OrganizationRoleDB)
        .options(
            selectinload(OrganizationRoleDB.responsibilities),
            selectinload(OrganizationRoleDB.goals),
            selectinload(OrganizationRoleDB.competencies),
        )
        .where(
            OrganizationRoleDB.id == role_id,
            OrganizationRoleDB.organization_id == organization_id,
        )
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company role not found.",
        )
    return role


def _role_response(role: OrganizationRoleDB) -> CompanyRoleResponse:
    return CompanyRoleResponse(
        id=role.id,
        name=role.name,
        summary=role.summary,
        responsibilities=[
            RoleResponsibilityResponse(
                id=item.id,
                statement=item.statement,
                position=item.position,
            )
            for item in role.responsibilities
        ],
        goals=[
            RoleGoalResponse(
                id=item.id,
                title=item.title,
                description=item.description,
                position=item.position,
            )
            for item in role.goals
        ],
        competencies=[
            RoleCompetencyResponse(
                id=item.id,
                name=item.name,
                expected_level=item.expected_level,
                description=item.description,
                position=item.position,
            )
            for item in role.competencies
        ],
        created_by_user_id=role.created_by_user_id,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def _snapshot(role: OrganizationRoleDB) -> dict:
    return _role_response(role).model_dump(mode="json")


def _set_role_fields(
    role: OrganizationRoleDB,
    request: CompanyRoleWriteRequest,
) -> None:
    role.name = request.name
    role.normalized_name = " ".join(request.name.split()).casefold()
    role.summary = request.summary
    role.responsibilities = [
        OrganizationRoleResponsibilityDB(
            id=str(uuid4()),
            statement=item.statement,
            position=index,
        )
        for index, item in enumerate(request.responsibilities)
    ]
    role.goals = [
        OrganizationRoleGoalDB(
            id=str(uuid4()),
            title=item.title,
            description=item.description,
            position=index,
        )
        for index, item in enumerate(request.goals)
    ]
    role.competencies = [
        OrganizationRoleCompetencyDB(
            id=str(uuid4()),
            name=item.name,
            expected_level=item.expected_level,
            description=item.description,
            position=index,
        )
        for index, item in enumerate(request.competencies)
    ]


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with that name already exists in this company.",
        ) from exc


def _audit_event(
    manager: UserDB,
    role: OrganizationRoleDB,
    action: str,
    before_snapshot: dict | None,
    after_snapshot: dict | None,
) -> OrganizationRoleAuditEventDB:
    return OrganizationRoleAuditEventDB(
        id=str(uuid4()),
        organization_id=manager.organization_id,
        role_id=role.id,
        role_name=role.name,
        action=action,
        actor_user_id=manager.id,
        actor_name=manager.name,
        actor_role=manager.role,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        created_at=datetime.now(UTC),
    )


@router.get("/roles", response_model=list[CompanyRoleResponse])
def list_company_roles(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[CompanyRoleResponse]:
    manager = _manager_for_company(current_user, db)
    roles = db.scalars(
        select(OrganizationRoleDB)
        .options(
            selectinload(OrganizationRoleDB.responsibilities),
            selectinload(OrganizationRoleDB.goals),
            selectinload(OrganizationRoleDB.competencies),
        )
        .where(OrganizationRoleDB.organization_id == manager.organization_id)
        .order_by(OrganizationRoleDB.normalized_name, OrganizationRoleDB.id)
    ).all()
    return [_role_response(role) for role in roles]


@router.post(
    "/roles",
    response_model=CompanyRoleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_company_role(
    request: CompanyRoleWriteRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CompanyRoleResponse:
    manager = _manager_for_company(current_user, db)
    now = datetime.now(UTC)
    role = OrganizationRoleDB(
        id=str(uuid4()),
        organization_id=manager.organization_id,
        name=request.name,
        normalized_name=" ".join(request.name.split()).casefold(),
        summary=request.summary,
        created_by_user_id=manager.id,
        created_at=now,
        updated_at=now,
    )
    _set_role_fields(role, request)
    db.add(role)
    db.add(_audit_event(manager, role, "CREATED", None, _snapshot(role)))
    _commit(db)
    return _role_response(_load_role(db, manager.organization_id, role.id))


@router.put("/roles/{role_id}", response_model=CompanyRoleResponse)
def update_company_role(
    role_id: str,
    request: CompanyRoleWriteRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CompanyRoleResponse:
    manager = _manager_for_company(current_user, db)
    role = _load_role(db, manager.organization_id, role_id)
    before_snapshot = _snapshot(role)
    role.responsibilities.clear()
    role.goals.clear()
    role.competencies.clear()
    db.flush()
    role.updated_at = datetime.now(UTC)
    _set_role_fields(role, request)
    db.add(
        _audit_event(
            manager,
            role,
            "UPDATED",
            before_snapshot,
            _snapshot(role),
        )
    )
    _commit(db)
    return _role_response(_load_role(db, manager.organization_id, role.id))


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company_role(
    role_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    manager = _manager_for_company(current_user, db)
    role = _load_role(db, manager.organization_id, role_id)
    before_snapshot = _snapshot(role)
    db.add(_audit_event(manager, role, "DELETED", before_snapshot, None))
    db.delete(role)
    _commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/history", response_model=list[CompanyRoleHistoryResponse])
def list_company_role_history(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    role_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[CompanyRoleHistoryResponse]:
    manager = _manager_for_company(current_user, db)
    query = select(OrganizationRoleAuditEventDB).where(
        OrganizationRoleAuditEventDB.organization_id == manager.organization_id
    )
    if role_id is not None:
        query = query.where(OrganizationRoleAuditEventDB.role_id == role_id)
    events = db.scalars(
        query.order_by(
            OrganizationRoleAuditEventDB.created_at.desc(),
            OrganizationRoleAuditEventDB.id.desc(),
        ).limit(limit)
    ).all()
    return [
        CompanyRoleHistoryResponse(
            id=event.id,
            role_id=event.role_id,
            role_name=event.role_name,
            action=event.action,
            actor_user_id=event.actor_user_id,
            actor_name=event.actor_name,
            actor_role=event.actor_role,
            before_snapshot=event.before_snapshot,
            after_snapshot=event.after_snapshot,
            created_at=event.created_at,
        )
        for event in events
    ]
