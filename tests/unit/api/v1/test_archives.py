from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.v1.archives import (
    get_evidence_mapping_service,
    get_evidence_service,
)
from app.api.v1.goals import get_goal_service
from app.api.v1.milestones import get_milestone_service
from app.db.models.goal import GoalDB
from app.main import app
from app.models.evidence import EvidenceStatus, EvidenceSourceType
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.services.evidence import EvidenceService
from app.services.evidence_mapping import EvidenceMappingService
from app.services.goal import GoalService
from app.services.milestone import MilestoneService

client = TestClient(app)


def _goal(status: GoalStatus = GoalStatus.ARCHIVED) -> GoalDB:
    now = datetime.now(UTC)
    return GoalDB(
        id="goal-1",
        user_id="user-1",
        title="Improve reliability",
        scope=GoalScope.PERSONAL,
        status=status,
        sub_status=GoalSubStatus.NONE if status == GoalStatus.ARCHIVED else GoalSubStatus.ON_TRACK,
        deactivation_reason="Priorities changed",
        created_at=now,
        updated_at=now,
    )


def _overrides(goal_service, evidence_service, mapping_service, milestone_service):
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    app.dependency_overrides[get_evidence_service] = lambda: evidence_service
    app.dependency_overrides[get_evidence_mapping_service] = lambda: mapping_service
    app.dependency_overrides[get_milestone_service] = lambda: milestone_service


def test_list_archives_returns_owned_archived_items():
    now = datetime.now(UTC)
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goals_by_user_id.return_value = [_goal()]
    evidence_service = MagicMock(spec=EvidenceService)
    evidence_service.get_evidence_by_user_id.return_value = [
        SimpleNamespace(
            id="evidence-1",
            user_id="user-1",
            title="Reduced incident rate",
            description="Fewer incidents",
            source_type=EvidenceSourceType.PERSONAL,
            source_url=None,
            captured_at=now,
            archived_at=now,
            status=EvidenceStatus.ARCHIVED,
        )
    ]
    mapping_service = MagicMock(spec=EvidenceMappingService)
    mapping_service.get_mappings_by_evidence_id.return_value = [
        SimpleNamespace(goal_id="goal-1")
    ]
    milestone_service = MagicMock(spec=MilestoneService)
    milestone_service.get_milestones_by_goal_id.return_value = [
        SimpleNamespace(
            id="milestone-1",
            title="Complete reliability review",
            description=None,
            completion_criteria=None,
            status="completed",
            due_date=None,
            archived_at=now,
        )
    ]
    _overrides(goal_service, evidence_service, mapping_service, milestone_service)
    try:
        response = client.get("/api/v1/archives", params={"user_id": "user-1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["goals"]] == ["goal-1"]
    assert payload["evidence"][0]["goal_titles"] == ["Improve reliability"]
    assert payload["milestones"][0]["goal_title"] == "Improve reliability"
    milestone_service.get_milestones_by_goal_id.assert_called_once_with(
        "goal-1",
        include_archived=True,
    )


def test_archive_evidence_enforces_ownership():
    evidence_service = MagicMock(spec=EvidenceService)
    evidence_service.get_evidence_by_id.return_value = SimpleNamespace(
        id="evidence-1",
        user_id="owner",
    )
    app.dependency_overrides[get_evidence_service] = lambda: evidence_service
    try:
        response = client.post(
            "/api/v1/evidence/evidence-1/archive",
            params={"user_id": "other-user"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    evidence_service.archive_evidence.assert_not_called()


def test_delete_evidence_requires_archived_status():
    evidence_service = MagicMock(spec=EvidenceService)
    evidence_service.get_evidence_by_id.return_value = SimpleNamespace(
        id="evidence-1",
        user_id="user-1",
        status=EvidenceStatus.ACTIVE,
    )
    app.dependency_overrides[get_evidence_service] = lambda: evidence_service
    try:
        response = client.delete(
            "/api/v1/evidence/evidence-1",
            params={"user_id": "user-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    evidence_service.delete_archived_evidence.assert_not_called()
