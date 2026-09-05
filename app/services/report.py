from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models.report import ReportDB
from app.models.report import ReportStatus, ReportType
from app.repositories.report import ReportRepository
from app.services.base import BaseService


class ReportService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = ReportRepository(session)

    def create_report(
        self,
        *,
        user_id: str,
        report_type: ReportType,
        period_start: date,
        period_end: date,
        content: str,
        version: int = 1,
        status: ReportStatus = ReportStatus.CURRENT,
    ) -> ReportDB:
        report = self.repository.create(
            report_id=str(uuid4()),
            user_id=user_id,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            content=content,
            version=version,
            status=status,
        )
        self.commit()
        return report

    def get_report_by_id(self, report_id: str) -> ReportDB | None:
        return self.repository.get_by_id(report_id)

    def get_reports_by_user_id(self, user_id: str) -> list[ReportDB]:
        return self.repository.get_by_user_id(user_id)

    def get_report_by_user_and_period(
        self,
        user_id: str,
        period_start: date,
        period_end: date,
    ) -> ReportDB | None:
        return self.repository.get_by_user_id_and_period(
            user_id,
            period_start,
            period_end,
        )
