from datetime import date
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.db.models.report import ReportDB
from app.models.report import ReportStatus, ReportType
from app.repositories.report import ReportRepository
from app.services.report import ReportService


def test_create_report():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ReportRepository)
    repository.create.return_value = MagicMock(spec=ReportDB)

    service = ReportService(session)
    service.repository = repository

    with patch(
        "app.services.report.uuid4",
        return_value="report-1",
    ):
        result = service.create_report(
            user_id="user-1",
            report_type=ReportType.MONTHLY_IMPACT,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            content="September impact report.",
        )

    assert isinstance(result, ReportDB)
    repository.create.assert_called_once_with(
        report_id="report-1",
        user_id="user-1",
        report_type=ReportType.MONTHLY_IMPACT,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        content="September impact report.",
        version=1,
        status=ReportStatus.CURRENT,
    )
    session.commit.assert_called_once()


def test_create_report_with_explicit_version_and_status():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ReportRepository)
    repository.create.return_value = MagicMock(spec=ReportDB)

    service = ReportService(session)
    service.repository = repository

    with patch(
        "app.services.report.uuid4",
        return_value="report-2",
    ):
        result = service.create_report(
            user_id="user-1",
            report_type=ReportType.MONTHLY_IMPACT,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            content="Archived August report.",
            version=2,
            status=ReportStatus.ARCHIVED,
        )

    assert isinstance(result, ReportDB)
    repository.create.assert_called_once_with(
        report_id="report-2",
        user_id="user-1",
        report_type=ReportType.MONTHLY_IMPACT,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        content="Archived August report.",
        version=2,
        status=ReportStatus.ARCHIVED,
    )
    session.commit.assert_called_once()


def test_get_report_by_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ReportRepository)
    expected = MagicMock(spec=ReportDB)
    repository.get_by_id.return_value = expected

    service = ReportService(session)
    service.repository = repository

    assert service.get_report_by_id("report-1") is expected
    repository.get_by_id.assert_called_once_with("report-1")


def test_get_reports_by_user_id():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ReportRepository)
    expected = [MagicMock(spec=ReportDB)]
    repository.get_by_user_id.return_value = expected

    service = ReportService(session)
    service.repository = repository

    assert service.get_reports_by_user_id("user-1") == expected
    repository.get_by_user_id.assert_called_once_with(
        "user-1",
        report_type=None,
    )


def test_get_report_by_user_and_period():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ReportRepository)
    expected = MagicMock(spec=ReportDB)
    repository.get_by_user_id_and_period.return_value = expected

    service = ReportService(session)
    service.repository = repository

    period_start = date(2026, 9, 1)
    period_end = date(2026, 9, 30)

    assert service.get_report_by_user_and_period(
        "user-1",
        period_start,
        period_end,
    ) is expected
    repository.get_by_user_id_and_period.assert_called_once_with(
        "user-1",
        period_start,
        period_end,
    )

def test_get_reports_by_user_id_with_report_type():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ReportRepository)

    expected_reports = [
        MagicMock(spec=ReportDB),
        MagicMock(spec=ReportDB),
    ]
    repository.get_by_user_id.return_value = expected_reports

    service = ReportService(session)
    service.repository = repository

    result = service.get_reports_by_user_id(
        "user-123",
        report_type=ReportType.MONTHLY_IMPACT,
    )

    assert result == expected_reports

    repository.get_by_user_id.assert_called_once_with(
        "user-123",
        report_type=ReportType.MONTHLY_IMPACT,
    )
    session.commit.assert_not_called()
    
    
def test_get_reports_by_user_id_without_report_type():
    session = MagicMock(spec=Session)
    repository = MagicMock(spec=ReportRepository)

    expected_reports = [MagicMock(spec=ReportDB)]
    repository.get_by_user_id.return_value = expected_reports

    service = ReportService(session)
    service.repository = repository

    result = service.get_reports_by_user_id("user-123")

    assert result == expected_reports

    repository.get_by_user_id.assert_called_once_with(
        "user-123",
        report_type=None,
    )
    session.commit.assert_not_called()