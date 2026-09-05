from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.report import ReportDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.report import ReportStatus, ReportType
from app.repositories.report import ReportRepository


@pytest.mark.integration
def test_create_and_get_reports():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    report_id = f"test-report-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Report Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        repository = ReportRepository(session)

        period_start = date(2026, 9, 1)
        period_end = date(2026, 9, 30)

        repository.create(
            report_id=report_id,
            user_id=user_id,
            report_type=ReportType.MONTHLY_IMPACT,
            period_start=period_start,
            period_end=period_end,
            content="September performance report.",
        )

        session.commit()

        result_by_id = repository.get_by_id(report_id)

        assert result_by_id is not None
        assert result_by_id.id == report_id
        assert result_by_id.user_id == user_id
        assert result_by_id.report_type == ReportType.MONTHLY_IMPACT
        assert result_by_id.period_start == period_start
        assert result_by_id.period_end == period_end
        assert result_by_id.content == "September performance report."
        assert result_by_id.version == 1
        assert result_by_id.status == ReportStatus.CURRENT

        user_reports = repository.get_by_user_id(user_id)

        assert len(user_reports) == 1
        assert user_reports[0].id == report_id

        period_report = repository.get_by_user_id_and_period(
            user_id,
            period_start,
            period_end,
        )

        assert period_report is not None
        assert period_report.id == report_id

    finally:
        session.execute(
            delete(ReportDB).where(ReportDB.id == report_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()


@pytest.mark.integration
def test_create_report_with_version_and_status():
    session = SessionLocal()

    user_id = f"test-user-{uuid4()}"
    report_id = f"test-report-{uuid4()}"

    try:
        user = UserDB(
            id=user_id,
            name="Report Version Test User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        session.add(user)
        session.commit()

        repository = ReportRepository(session)

        repository.create(
            report_id=report_id,
            user_id=user_id,
            report_type=ReportType.MONTHLY_IMPACT,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            content="Archived August report.",
            version=2,
            status=ReportStatus.ARCHIVED,
        )

        session.commit()

        result = repository.get_by_id(report_id)

        assert result is not None
        assert result.version == 2
        assert result.status == ReportStatus.ARCHIVED

    finally:
        session.execute(
            delete(ReportDB).where(ReportDB.id == report_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )
        session.commit()
        session.close()