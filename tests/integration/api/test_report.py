from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models.report import ReportDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.main import app
from app.models.user import UserCreate
from app.services.user import UserService

client = TestClient(app)


@pytest.mark.integration
def test_report_api_create_and_get_by_period():
    session = SessionLocal()
    user_id = None
    report_id = None
    try:
        user = UserService(session).create_user(UserCreate(name="Report API User", email=f"{uuid4()}@example.com"))
        user_id = user.id
        response = client.post("/reports", json={"user_id": user_id, "report_type": "monthly_impact", "period_start": "2026-09-01", "period_end": "2026-09-30", "content": "September report"})
        assert response.status_code == 201
        report_id = response.json()["id"]
        response = client.get(f"/reports/{report_id}")
        assert response.status_code == 200
        response = client.get(f"/reports/user/{user_id}/period", params={"period_start": "2026-09-01", "period_end": "2026-09-30"})
        assert response.status_code == 200
        assert response.json()["id"] == report_id
    finally:
        if report_id:
            session.execute(delete(ReportDB).where(ReportDB.id == report_id))
        if user_id:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()


@pytest.mark.integration
def test_report_api_missing_returns_404():
    assert client.get("/reports/missing-report").status_code == 404

@pytest.mark.integration
def test_report_api_filters_by_report_type():
    session = SessionLocal()

    user_id = None
    monthly_report_id = None
    quarterly_report_id = None

    try:
        user = UserService(session).create_user(
            UserCreate(
                name="Report Filter User",
                email=f"{uuid4()}@example.com",
            )
        )
        user_id = user.id

        monthly_response = client.post(
            "/reports",
            json={
                "user_id": user_id,
                "report_type": "monthly_impact",
                "period_start": "2026-09-01",
                "period_end": "2026-09-30",
                "content": "Monthly impact report",
            },
        )

        quarterly_response = client.post(
            "/reports",
            json={
                "user_id": user_id,
                "report_type": "quarterly_impact",
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "content": "Quarterly impact report",
            },
        )

        assert monthly_response.status_code == 201
        assert quarterly_response.status_code == 201

        monthly_report_id = monthly_response.json()["id"]
        quarterly_report_id = quarterly_response.json()["id"]

        response = client.get(
            f"/reports/user/{user_id}",
            params={"report_type": "monthly_impact"},
        )

        assert response.status_code == 200

        reports = response.json()

        assert len(reports) == 1
        assert reports[0]["id"] == monthly_report_id
        assert reports[0]["report_type"] == "monthly_impact"

    finally:
        if monthly_report_id is not None:
            session.execute(
                delete(ReportDB).where(
                    ReportDB.id == monthly_report_id
                )
            )

        if quarterly_report_id is not None:
            session.execute(
                delete(ReportDB).where(
                    ReportDB.id == quarterly_report_id
                )
            )

        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )

        session.commit()
        session.close()
        
        
        
