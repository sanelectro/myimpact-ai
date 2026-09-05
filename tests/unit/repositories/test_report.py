from datetime import UTC, date
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.report import ReportDB
from app.models.report import ReportStatus, ReportType
from app.repositories.report import ReportRepository


def test_get_by_id_returns_report():
    session = MagicMock(spec=Session)
    expected_report = MagicMock(spec=ReportDB)

    session.get.return_value = expected_report

    repository = ReportRepository(session)

    result = repository.get_by_id("report-123")

    assert result is expected_report
    session.get.assert_called_once_with(
        ReportDB,
        "report-123",
    )


def test_get_by_id_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    session.get.return_value = None

    repository = ReportRepository(session)

    result = repository.get_by_id("missing-report")

    assert result is None
    session.get.assert_called_once_with(
        ReportDB,
        "missing-report",
    )


def test_get_by_user_id_returns_reports():
    session = MagicMock(spec=Session)

    report_1 = MagicMock(spec=ReportDB)
    report_2 = MagicMock(spec=ReportDB)

    expected_reports = [report_1, report_2]

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = expected_reports

    repository = ReportRepository(session)

    result = repository.get_by_user_id("user-123")

    assert result == expected_reports
    session.query.assert_called_once_with(ReportDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()


def test_get_by_user_id_returns_empty_list_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = []

    repository = ReportRepository(session)

    result = repository.get_by_user_id("missing-user")

    assert result == []
    session.query.assert_called_once_with(ReportDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()


def test_get_by_user_id_and_period_returns_report():
    session = MagicMock(spec=Session)
    expected_report = MagicMock(spec=ReportDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = expected_report

    repository = ReportRepository(session)

    period_start = date(2026, 9, 1)
    period_end = date(2026, 9, 30)

    result = repository.get_by_user_id_and_period(
        "user-123",
        period_start,
        period_end,
    )

    assert result is expected_report
    session.query.assert_called_once_with(ReportDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()

    filter_arguments = query.filter.call_args.args

    assert len(filter_arguments) == 3
    assert filter_arguments[0].right.value == "user-123"
    assert filter_arguments[1].right.value == period_start
    assert filter_arguments[2].right.value == period_end


def test_get_by_user_id_and_period_returns_none_when_not_found():
    session = MagicMock(spec=Session)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.first.return_value = None

    repository = ReportRepository(session)

    result = repository.get_by_user_id_and_period(
        "missing-user",
        date(2026, 9, 1),
        date(2026, 9, 30),
    )

    assert result is None
    session.query.assert_called_once_with(ReportDB)
    query.filter.assert_called_once()
    filtered_query.first.assert_called_once()


def test_create_report():
    session = MagicMock(spec=Session)
    repository = ReportRepository(session)

    period_start = date(2026, 9, 1)
    period_end = date(2026, 9, 30)

    result = repository.create(
        report_id="report-123",
        user_id="user-123",
        report_type=ReportType.MONTHLY_IMPACT,
        period_start=period_start,
        period_end=period_end,
        content="September performance report.",
    )

    assert isinstance(result, ReportDB)
    assert result.id == "report-123"
    assert result.user_id == "user-123"
    assert result.report_type == ReportType.MONTHLY_IMPACT
    assert result.period_start == period_start
    assert result.period_end == period_end
    assert result.content == "September performance report."
    assert result.version == 1
    assert result.status == ReportStatus.CURRENT

    assert result.generated_at is not None
    assert result.updated_at is not None
    assert result.generated_at.tzinfo == UTC
    assert result.updated_at.tzinfo == UTC

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()


def test_create_report_with_explicit_version_and_status():
    session = MagicMock(spec=Session)
    repository = ReportRepository(session)

    period_start = date(2026, 8, 1)
    period_end = date(2026, 8, 31)

    result = repository.create(
        report_id="report-456",
        user_id="user-123",
        report_type=ReportType.MONTHLY_IMPACT,
        period_start=period_start,
        period_end=period_end,
        content="Updated August performance report.",
        version=2,
        status=ReportStatus.ARCHIVED,
    )

    assert isinstance(result, ReportDB)
    assert result.id == "report-456"
    assert result.user_id == "user-123"
    assert result.report_type == ReportType.MONTHLY_IMPACT
    assert result.period_start == period_start
    assert result.period_end == period_end
    assert result.content == "Updated August performance report."
    assert result.version == 2
    assert result.status == ReportStatus.ARCHIVED

    assert result.generated_at is not None
    assert result.updated_at is not None

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()
    
    
    
def test_get_by_user_id_filters_by_report_type():
    session = MagicMock(spec=Session)

    report_1 = MagicMock(spec=ReportDB)
    report_2 = MagicMock(spec=ReportDB)

    query = session.query.return_value
    user_filtered_query = query.filter.return_value
    type_filtered_query = user_filtered_query.filter.return_value
    type_filtered_query.all.return_value = [report_1, report_2]

    repository = ReportRepository(session)

    result = repository.get_by_user_id(
        "user-123",
        report_type=ReportType.MONTHLY_IMPACT,
    )

    assert result == [report_1, report_2]

    session.query.assert_called_once_with(ReportDB)
    assert query.filter.call_count == 1
    assert user_filtered_query.filter.call_count == 1
    type_filtered_query.all.assert_called_once()
    
    
def test_get_by_user_id_without_report_type_returns_all_reports():
    session = MagicMock(spec=Session)

    report_1 = MagicMock(spec=ReportDB)
    report_2 = MagicMock(spec=ReportDB)

    query = session.query.return_value
    filtered_query = query.filter.return_value
    filtered_query.all.return_value = [report_1, report_2]

    repository = ReportRepository(session)

    result = repository.get_by_user_id("user-123")

    assert result == [report_1, report_2]

    session.query.assert_called_once_with(ReportDB)
    query.filter.assert_called_once()
    filtered_query.all.assert_called_once()