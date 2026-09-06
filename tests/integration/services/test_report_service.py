from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.report import ReportDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.report import ReportStatus, ReportType
from app.models.user import UserCreate
from app.services.report import ReportService
from app.services.user import UserService


@pytest.mark.integration
def test_create_and_get_report():
    session = SessionLocal()
    user_id = None
    report_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Report Service User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id

        service = ReportService(session)

        report = service.create_report(
            user_id=user_id,
            report_type=ReportType.MONTHLY_IMPACT,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            content="September impact report.",
        )
        report_id = report.id

        result = service.get_report_by_user_and_period(
            user_id,
            date(2026, 9, 1),
            date(2026, 9, 30),
        )

        assert result is not None
        assert result.id == report_id
        assert result.report_type == ReportType.MONTHLY_IMPACT
        assert result.status == ReportStatus.CURRENT
        assert result.version == 1

    finally:
        if report_id is not None:
            session.execute(
                delete(ReportDB).where(ReportDB.id == report_id)
            )
        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
        session.commit()
        session.close()
