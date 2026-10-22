from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.goals import get_goal_service
from app.api.v1.milestones import get_milestone_service
from app.db.base import Base
from app.db.models.goal import GoalDB
from app.db.models.milestone import MilestoneDB
from app.db.models.user import UserDB
from app.db.session import get_db
from app.main import app
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.services.goal import GoalService
from app.services.milestone import MilestoneService

client = TestClient(app)


def _goal(user_id: str = "user-1") -> GoalDB:
    now = datetime.now(UTC)
    return GoalDB(
        id="goal-1",
        user_id=user_id,
        title="Improve reliability",
        scope=GoalScope.PERSONAL,
        status=GoalStatus.ACTIVE,
        sub_status=GoalSubStatus.ON_TRACK,
        created_at=now,
        updated_at=now,
    )


def _milestone(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": "milestone-1",
        "goal_id": "goal-1",
        "title": "Assess current architecture",
        "description": "Document current risks",
        "completion_criteria": "Findings are reviewed",
        "status": "not_started",
        "due_date": date(2026, 12, 1),
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _overrides(goal_service, milestone_service):
    app.dependency_overrides[get_goal_service] = lambda: goal_service
    app.dependency_overrides[get_milestone_service] = lambda: milestone_service


def test_list_milestones_checks_goal_ownership():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal(user_id="owner")
    milestone_service = MagicMock(spec=MilestoneService)
    _overrides(goal_service, milestone_service)
    try:
        response = client.get(
            "/api/v1/goals/goal-1/milestones",
            params={"user_id": "other-user"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    milestone_service.get_milestones_by_goal_id.assert_not_called()


def test_create_milestone_returns_goal_linked_milestone():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal()
    milestone_service = MagicMock(spec=MilestoneService)
    milestone_service.create_milestone.return_value = _milestone()
    _overrides(goal_service, milestone_service)
    try:
        response = client.post(
            "/api/v1/goals/goal-1/milestones",
            params={"user_id": "user-1"},
            json={"title": "Assess current architecture"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["goal_id"] == "goal-1"
    assert response.json()["status"] == "not_started"


def test_update_milestone_changes_status_without_changing_goal():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal()
    milestone_service = MagicMock(spec=MilestoneService)
    milestone_service.update_milestone.return_value = _milestone(status="completed")
    _overrides(goal_service, milestone_service)
    try:
        response = client.put(
            "/api/v1/goals/goal-1/milestones/milestone-1",
            params={"user_id": "user-1"},
            json={"status": "completed"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    goal_service.transition_status.assert_not_called()
    milestone_service.update_milestone.assert_called_once_with(
        "goal-1",
        "milestone-1",
        {"status": "completed"},
    )


def test_create_milestone_rejects_blank_title():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal()
    milestone_service = MagicMock(spec=MilestoneService)
    _overrides(goal_service, milestone_service)
    try:
        response = client.post(
            "/api/v1/goals/goal-1/milestones",
            params={"user_id": "user-1"},
            json={"title": "   "},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    milestone_service.create_milestone.assert_not_called()


def test_archive_milestone_checks_goal_ownership_and_archives():
    goal_service = MagicMock(spec=GoalService)
    goal_service.get_goal_by_id.return_value = _goal()
    milestone_service = MagicMock(spec=MilestoneService)
    milestone_service.archive_milestone.return_value = _milestone(
        archived_at=datetime.now(UTC),
    )
    _overrides(goal_service, milestone_service)
    try:
        response = client.post(
            "/api/v1/goals/goal-1/milestones/milestone-1/archive",
            params={"user_id": "user-1"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["archived_at"] is not None
    milestone_service.archive_milestone.assert_called_once_with(
        "goal-1",
        "milestone-1",
    )


def test_goal_milestone_flow_persists_without_changing_goal_assessment_state():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[UserDB.__table__, GoalDB.__table__, MilestoneDB.__table__],
    )
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with test_session_factory() as session:
        now = datetime.now(UTC)
        session.add(UserDB(
            id="user-1",
            name="Milestone Test User",
            email="milestone-test@example.com",
            created_at=now,
            updated_at=now,
        ))
        session.add(_goal())
        session.commit()

    def override_get_db():
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        created = client.post(
            "/api/v1/goals/goal-1/milestones",
            params={"user_id": "user-1"},
            json={
                "title": "Assess current architecture",
                "completion_criteria": "Findings are reviewed",
            },
        )
        assert created.status_code == 201
        milestone_id = created.json()["id"]

        updated = client.put(
            f"/api/v1/goals/goal-1/milestones/{milestone_id}",
            params={"user_id": "user-1"},
            json={"status": "in_progress"},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "in_progress"

        listed = client.get(
            "/api/v1/goals/goal-1/milestones",
            params={"user_id": "user-1"},
        )
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == milestone_id

        unchanged_goal = client.get(
            "/api/v1/goals/goal-1",
            params={"user_id": "user-1"},
        )
        assert unchanged_goal.status_code == 200
        assert unchanged_goal.json()["status"] == "active"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
