from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.report import Report, ReportStatus, ReportType
from app.services.report import ReportService


class ReportCreateRequest(BaseModel):
    user_id: str
    report_type: ReportType
    period_start: date
    period_end: date
    content: str
    version: int = Field(default=1, ge=1)
    status: ReportStatus = ReportStatus.CURRENT


router = APIRouter(prefix="/reports", tags=["reports"])


def get_report_service(
    db: Annotated[Session, Depends(get_db)],
) -> ReportService:
    return ReportService(db)


@router.post(
    "",
    response_model=Report,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    request: ReportCreateRequest,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> Report:
    report = service.create_report(
        user_id=request.user_id,
        report_type=request.report_type,
        period_start=request.period_start,
        period_end=request.period_end,
        content=request.content,
        version=request.version,
        status=request.status,
    )

    return Report.model_validate(
        report,
        from_attributes=True,
    )


@router.get(
    "/user/{user_id}/period",
    response_model=Report,
)
def get_report_by_user_and_period(
    user_id: str,
    period_start: Annotated[date, Query()],
    period_end: Annotated[date, Query()],
    service: Annotated[ReportService, Depends(get_report_service)],
) -> Report:
    report = service.get_report_by_user_and_period(
        user_id,
        period_start,
        period_end,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return Report.model_validate(
        report,
        from_attributes=True,
    )


@router.get(
    "/user/{user_id}",
    response_model=list[Report],
)
def get_reports_by_user_id(
    user_id: str,
    report_type: Annotated[ReportType | None, Query()] = None,
    service: Annotated[ReportService, Depends(get_report_service)] = None,
) -> list[Report]:
    reports = service.get_reports_by_user_id(
        user_id,
        report_type=report_type,
    )

    return [
        Report.model_validate(
            report,
            from_attributes=True,
        )
        for report in reports
    ]


@router.get(
    "/{report_id}",
    response_model=Report,
)
def get_report_by_id(
    report_id: str,
    service: Annotated[ReportService, Depends(get_report_service)],
) -> Report:
    report = service.get_report_by_id(report_id)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return Report.model_validate(
        report,
        from_attributes=True,
    )