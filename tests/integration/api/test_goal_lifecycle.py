import json
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.v1.goals import get_goal_validation_service
from app.db.models.goal import GoalDB
from app.db.models.goal_status_history import GoalStatusHistoryDB
from app.db.models.organization import OrganizationDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.llm import LLMResponse
from app.models.user import UserCreate
from app.services.goal_validation_runs import GoalValidationRunService
from app.services.user import UserService

client = TestClient(app)


class _ReadyLLM:
    async def generate(self, request):
        return LLMResponse(
            content=json.dumps({"issues": []}),
            model="test-model",
            provider="test-provider",
        )


def _goal_validation_service_with_ready_llm(
    db: Annotated[Session, Depends(get_db)],
) -> GoalValidationRunService:
    return GoalValidationRunService(db, _ReadyLLM())


@pytest.mark.integration
def test_goal_api_crud_assessment_isolation_and_full_lifecycle():
    session = SessionLocal()
    user_id = None
    goal_id = None
    organization_id = None

    try:
        app.dependency_overrides[get_goal_validation_service] = (
            _goal_validation_service_with_ready_llm
        )
        user = UserService(session).create_user(
            UserCreate(
                name="M6.3 Lifecycle API User",
                email=f"{uuid4()}@example.com",
                role="Engineer",
            )
        )
        user_id = user.id
        organization_id = str(uuid4())
        session.add(
            OrganizationDB(
                id=organization_id,
                name=f"M6.3 Test Organization {organization_id}",
                normalized_name=organization_id,
                created_at=user.created_at,
            )
        )
        user.organization_id = organization_id
        session.commit()

        created = client.post(
            "/api/v1/goals",
            params={"user_id": user_id},
            json={
                "title": "Improve deployment reliability",
                "scope": "team",
            },
        )
        assert created.status_code == 201
        goal = created.json()
        goal_id = goal["id"]
        assert goal["status"] == "draft"
        assert goal["sub_status"] == "needs_review"
        assert goal["scope"] == "team"

        listed = client.get("/api/v1/goals", params={"user_id": user_id})
        assert listed.status_code == 200
        assert any(item["id"] == goal_id for item in listed.json())

        viewed = client.get(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": user_id},
        )
        assert viewed.status_code == 200
        assert viewed.json()["title"] == "Improve deployment reliability"

        updated = client.put(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": f"not-{user_id}"},
            json={"title": "Unauthorized change"},
        )
        assert updated.status_code == 404

        updated = client.put(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": user_id},
            json={
                "title": "Improve deployment reliability by 30%",
                "scope": "organization",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Improve deployment reliability by 30%"
        assert updated.json()["scope"] == "organization"

        validation = client.post(
            f"/api/v1/goals/{goal_id}/validate",
            params={"user_id": user_id},
        )
        assert validation.status_code == 201, validation.text
        validation_result = validation.json()
        assert validation_result["status"] == "NEEDS_IMPROVEMENT"
        findings_by_code = {
            finding["finding_code"]: finding
            for finding in validation_result["findings"]
        }
        assert "missing_accountability" in findings_by_code
        assert findings_by_code["missing_accountability"]["missing_info"] == [
            "accountability"
        ]
        assert "missing_success_criteria" in findings_by_code
        assert findings_by_code["missing_success_criteria"]["missing_info"] == [
            "success_criteria"
        ]

        completed_definition = client.put(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": user_id},
            json={
                "structured_fields": {
                    "accountability": "Platform engineering lead",
                    "success_criteria": [
                        {
                            "criterion_type": "BINARY",
                            "description": "Deployment reliability improves",
                            "completion_conditions": (
                                "The deployment reliability target is met."
                            ),
                        }
                    ],
                }
            },
        )
        assert completed_definition.status_code == 200
        ready_validation = client.post(
            f"/api/v1/goals/{goal_id}/validate",
            params={"user_id": user_id},
        )
        assert ready_validation.status_code == 201, ready_validation.text
        assert ready_validation.json()["status"] == "READY"

        assessment = client.get(
            f"/api/v1/goals/{goal_id}/assessment",
            params={"user_id": user_id},
        )
        assert assessment.status_code == 200
        assert assessment.json()["criteria_count"] == 0
        assert assessment.json()["criteria_met_count"] == 0
        assert assessment.json()["goal_progress_percentage"] is None

        wrong_owner = client.get(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": f"not-{user_id}"},
        )
        assert wrong_owner.status_code == 404

        invalid_transition = client.post(
            f"/api/v1/goals/{goal_id}/complete",
            params={"user_id": user_id},
        )
        assert invalid_transition.status_code == 422

        transitions = (
            ("approve", "approved", "not_started"),
            ("activate", "active", "on_track"),
        )
        for action, expected_status, expected_sub_status in transitions:
            response = client.post(
                f"/api/v1/goals/{goal_id}/{action}",
                params={"user_id": user_id},
            )
            assert response.status_code == 200
            assert response.json()["status"] == expected_status
            assert response.json()["sub_status"] == expected_sub_status

        revision = client.put(
            f"/api/v1/goals/{goal_id}",
            params={"user_id": user_id},
            json={"title": "Improve deployment reliability by 40%"},
        )
        assert revision.status_code == 200
        assert revision.json()["status"] == "active"
        revalidation = client.post(
            f"/api/v1/goals/{goal_id}/validate",
            params={"user_id": user_id},
        )
        assert revalidation.status_code == 201
        reapproval = client.post(
            f"/api/v1/goals/{goal_id}/approve",
            params={"user_id": user_id},
        )
        assert reapproval.status_code == 200
        assert reapproval.json()["status"] == "active"

        completed = client.post(
            f"/api/v1/goals/{goal_id}/complete",
            params={"user_id": user_id},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["sub_status"] == "completed"

        archived = client.post(
            f"/api/v1/goals/{goal_id}/deactivate",
            params={"user_id": user_id},
            json={"reason": "Goal cycle complete"},
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"
        assert archived.json()["sub_status"] == "none"
        assert archived.json()["deactivation_reason"] == "Goal cycle complete"

        history = client.get(
            f"/api/v1/goals/{goal_id}/history",
            params={"user_id": user_id},
        )
        assert history.status_code == 200
        assert [entry["to_status"] for entry in history.json()] == [
            "archived",
            "completed",
            "active",
            "approved",
        ]
    finally:
        if goal_id is not None:
            session.execute(
                delete(GoalStatusHistoryDB).where(
                    GoalStatusHistoryDB.goal_id == goal_id
                )
            )
            session.execute(delete(GoalDB).where(GoalDB.id == goal_id))
        if user_id is not None:
            session.execute(delete(UserDB).where(UserDB.id == user_id))
        if organization_id is not None:
            session.execute(
                delete(OrganizationDB).where(OrganizationDB.id == organization_id)
            )
        session.commit()
        session.close()
        app.dependency_overrides.clear()
