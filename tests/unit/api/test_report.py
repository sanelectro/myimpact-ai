from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.routes.report import get_report_service
from app.db.models.report import ReportDB
from app.main import app
from app.models.report import ReportStatus, ReportType
from app.services.report import ReportService

client = TestClient(app)


def _report():
    now = datetime.now(UTC)
    return ReportDB(id="report-1", user_id="user-1", report_type=ReportType.MONTHLY_IMPACT, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30), content="September report", version=1, status=ReportStatus.CURRENT, generated_at=now, updated_at=now)


def test_create_report():
    service = MagicMock(spec=ReportService)
    service.create_report.return_value = _report()
    app.dependency_overrides[get_report_service] = lambda: service
    try:
        response = client.post("/reports", json={"user_id": "user-1", "report_type": "monthly_impact", "period_start": "2026-09-01", "period_end": "2026-09-30", "content": "September report"})
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


def test_get_report_by_id():
    service = MagicMock(spec=ReportService)
    service.get_report_by_id.return_value = _report()
    app.dependency_overrides[get_report_service] = lambda: service
    try:
        assert client.get("/reports/report-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_report_by_id_returns_404():
    service = MagicMock(spec=ReportService)
    service.get_report_by_id.return_value = None
    app.dependency_overrides[get_report_service] = lambda: service
    try:
        assert client.get("/reports/missing").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_reports_by_user_id():
    service = MagicMock(spec=ReportService)
    service.get_reports_by_user_id.return_value = [_report()]
    app.dependency_overrides[get_report_service] = lambda: service
    try:
        assert client.get("/reports/user/user-1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_report_by_user_and_period():
    service = MagicMock(spec=ReportService)
    service.get_report_by_user_and_period.return_value = _report()
    app.dependency_overrides[get_report_service] = lambda: service
    try:
        response = client.get("/reports/user/user-1/period", params={"period_start": "2026-09-01", "period_end": "2026-09-30"})
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_report_by_user_and_period_returns_404():
    service = MagicMock(spec=ReportService)
    service.get_report_by_user_and_period.return_value = None
    app.dependency_overrides[get_report_service] = lambda: service
    try:
        response = client.get("/reports/user/user-1/period", params={"period_start": "2026-09-01", "period_end": "2026-09-30"})
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()

def test_get_reports_by_user_id_with_report_type():
    service = MagicMock(spec=ReportService)
    service.get_reports_by_user_id.return_value = [_report()]

    app.dependency_overrides[get_report_service] = lambda: service

    try:
        response = client.get(
            "/reports/user/user-1",
            params={"report_type": "monthly_impact"},
        )

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["report_type"] == "monthly_impact"

        service.get_reports_by_user_id.assert_called_once_with(
            "user-1",
            report_type=ReportType.MONTHLY_IMPACT,
        )
    finally:
        app.dependency_overrides.clear()
        
        
def test_get_reports_by_user_id_without_report_type():
    service = MagicMock(spec=ReportService)
    service.get_reports_by_user_id.return_value = [_report()]

    app.dependency_overrides[get_report_service] = lambda: service

    try:
        response = client.get("/reports/user/user-1")

        assert response.status_code == 200
        assert len(response.json()) == 1

        service.get_reports_by_user_id.assert_called_once_with(
            "user-1",
            report_type=None,
        )
    finally:
        app.dependency_overrides.clear()
        
        
