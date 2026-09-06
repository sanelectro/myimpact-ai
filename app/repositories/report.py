from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.db.models.report import ReportDB
from app.models.report import ReportStatus, ReportType
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)

    def get_by_id(self, report_id: str) -> ReportDB | None:
        return self.session.get(ReportDB, report_id)

    def get_by_user_id(
        self,
        user_id: str,
        report_type: ReportType | None = None,
    ) -> list[ReportDB]:
        query = (
            self.session.query(ReportDB)
            .filter(ReportDB.user_id == user_id)
        )

        if report_type is not None:
            query = query.filter(ReportDB.report_type == report_type)

        return query.all()

    def get_by_user_id_and_period(
        self,
        user_id: str,
        period_start: date,
        period_end: date,
    ) -> ReportDB | None:
        return (
            self.session.query(ReportDB)
            .filter(
                ReportDB.user_id == user_id,
                ReportDB.period_start == period_start,
                ReportDB.period_end == period_end,
            )
            .first()
        )

    def create(
        self,
        *,
        report_id: str,
        user_id: str,
        report_type: ReportType,
        period_start: date,
        period_end: date,
        content: str,
        version: int = 1,
        status: ReportStatus = ReportStatus.CURRENT,
    ) -> ReportDB:
        now = datetime.now(UTC)

        report = ReportDB(
            id=report_id,
            user_id=user_id,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            content=content,
            version=version,
            status=status,
            generated_at=now,
            updated_at=now,
        )

        self.session.add(report)
        self.session.flush()

        return report