from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser, get_current_user
from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_approval import EvidenceApprovalDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.goal import GoalDB
from app.db.models.milestone import MilestoneDB
from app.db.models.notification import NotificationDB
from app.db.models.notification_history import NotificationHistoryDB
from app.db.models.notification_response import NotificationResponseDB
from app.db.models.organization import OrganizationDB
from app.db.models.user import UserDB
from app.db.session import get_db
from app.main import app
from app.models.evidence import EvidenceSourceType
from app.models.evidence_approval import EvidenceApprovalStatus
from app.models.evidence_mapping import EvidenceRelevance
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.models.milestone import MilestoneStatus
from app.models.notification import NotificationStatus


def test_manager_reviews_only_direct_report_and_notifies_employee():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        OrganizationDB.__table__,
        UserDB.__table__,
        GoalDB.__table__,
        MilestoneDB.__table__,
        EvidenceDB.__table__,
        EvidenceMappingDB.__table__,
        EvidenceApprovalDB.__table__,
        NotificationDB.__table__,
        NotificationResponseDB.__table__,
        NotificationHistoryDB.__table__,
    ]
    for table in tables:
        table.create(engine)
    db = sessionmaker(bind=engine, class_=Session)()
    now = datetime.now(UTC)
    manager = UserDB(
        id="manager",
        name="Reporting Manager",
        email="manager@example.test",
        role="Engineering Manager",
        created_at=now,
        updated_at=now,
    )
    other_manager = UserDB(
        id="other-manager",
        name="Other Manager",
        email="other-manager@example.test",
        role="Engineering Manager",
        created_at=now,
        updated_at=now,
    )
    employee = UserDB(
        id="employee",
        name="Team Member",
        email="employee@example.test",
        role="Software Engineer",
        reporting_manager_id=manager.id,
        created_at=now,
        updated_at=now,
    )
    goal = GoalDB(
        id="goal",
        user_id=employee.id,
        title="Improve reliability",
        description="Reduce incidents",
        scope=GoalScope.PERSONAL,
        status=GoalStatus.ACTIVE,
        sub_status=GoalSubStatus.ON_TRACK,
        created_at=now,
        updated_at=now,
    )
    milestone = MilestoneDB(
        id="milestone",
        goal_id=goal.id,
        title="Automate release checks",
        description="Add CI verification",
        completion_criteria="Checks pass",
        status=MilestoneStatus.IN_PROGRESS,
        created_at=now,
        updated_at=now,
    )
    evidence = EvidenceDB(
        id="evidence",
        user_id=employee.id,
        source_type=EvidenceSourceType.PERSONAL,
        title="Release verification",
        description="Added an automated release workflow.",
        captured_at=now,
        created_at=now,
        updated_at=now,
    )
    mapping = EvidenceMappingDB(
        id="mapping",
        evidence_id=evidence.id,
        goal_id=goal.id,
        milestone_id=milestone.id,
        relevance=EvidenceRelevance.HIGH,
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )
    approval = EvidenceApprovalDB(
        id="approval",
        mapping_id=mapping.id,
        status=EvidenceApprovalStatus.PENDING,
        created_at=now,
    )
    db.add_all(
        [manager, other_manager, employee, goal, milestone, evidence, mapping, approval]
    )
    db.commit()

    def override_db():
        yield db

    def use_user(user: UserDB):
        return AuthenticatedUser(
            user.id,
            user.email,
            user.role,
            {"myimpact-ai"},
            user.name,
        )

    previous_db_override = app.dependency_overrides.get(get_db)
    previous_user_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: use_user(manager)
    client = TestClient(app)
    try:
        queue = client.get("/api/v1/evidence-approvals/pending")
        assert queue.status_code == 200
        assert len(queue.json()) == 1
        assert queue.json()[0]["goal_title"] == goal.title
        assert queue.json()[0]["milestone_completion_criteria"] == "Checks pass"
        assert queue.json()[0]["evidence_title"] == evidence.title

        app.dependency_overrides[get_current_user] = lambda: use_user(other_manager)
        other_queue = client.get("/api/v1/evidence-approvals/pending")
        assert other_queue.status_code == 200
        assert other_queue.json() == []
        forbidden = client.post(
            f"/api/v1/evidence-approvals/{approval.id}/decision",
            json={"decision": "approved"},
        )
        assert forbidden.status_code == 403

        app.dependency_overrides[get_current_user] = lambda: use_user(manager)
        decision = client.post(
            f"/api/v1/evidence-approvals/{approval.id}/decision",
            json={"decision": "needs_information", "comment": "Please add the test run."},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "needs_information"
        assert db.get(EvidenceApprovalDB, approval.id).status == (
            EvidenceApprovalStatus.NEEDS_INFORMATION
        )

        app.dependency_overrides[get_current_user] = lambda: use_user(employee)
        notifications = client.get("/api/v1/notifications")
        assert notifications.status_code == 200
        assert notifications.json()[0]["status"] == "unread"
        assert "Please add the test run." in notifications.json()[0]["message"]
        assert notifications.json()[0]["metadata"]["reason"] == "needs_information"

        marked_read = client.patch(
            f"/api/v1/notifications/{notifications.json()[0]['id']}/read"
        )
        assert marked_read.status_code == 200
        assert marked_read.json()["status"] == "read"
        assert db.get(NotificationDB, notifications.json()[0]["id"]).status == (
            NotificationStatus.READ
        )
        read_history = db.query(NotificationHistoryDB).filter_by(
            notification_id=notifications.json()[0]["id"],
            event_type="notification_read",
        ).one()
        assert read_history.metadata_json["status"] == "read"

        updated_evidence = client.post(
            f"/api/v1/evidence-approvals/{approval.id}/resubmit",
            json={
                "title": "Release verification with CI proof",
                "description": "Added the CI run and verification details.",
                "source_url": "https://example.test/ci/run/123",
                "notes": "The successful test run is now linked.",
            },
        )
        assert updated_evidence.status_code == 200
        assert updated_evidence.json()["status"] == "pending"
        assert updated_evidence.json()["evidence_id"] == evidence.id
        assert db.get(EvidenceDB, evidence.id).title == "Release verification with CI proof"

        app.dependency_overrides[get_current_user] = lambda: use_user(manager)
        manager_notifications = client.get("/api/v1/notifications")
        assert manager_notifications.status_code == 200
        resubmission_notification = manager_notifications.json()[0]
        assert resubmission_notification["title"] == "Evidence resubmitted"
        assert resubmission_notification["responses"][0]["response_text"] == (
            "The successful test run is now linked."
        )
        assert resubmission_notification["history"][0]["event_type"] == (
            "employee_resubmitted"
        )
        assert client.get("/api/v1/evidence-approvals/pending").json()[0][
            "evidence_title"
        ] == "Release verification with CI proof"

        second_decision = client.post(
            f"/api/v1/evidence-approvals/{approval.id}/decision",
            json={"decision": "approved", "comment": "Verified."},
        )
        assert second_decision.status_code == 200
        assert second_decision.json()["status"] == "approved"
    finally:
        if previous_db_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db_override
        if previous_user_override is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous_user_override
        db.close()
        engine.dispose()
