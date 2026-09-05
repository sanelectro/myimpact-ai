from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.evidence import EvidenceDB
from app.db.models.evidence_mapping import EvidenceMappingDB
from app.db.models.evidence_version import EvidenceVersionDB
from app.db.models.goal import GoalDB
from app.db.models.impact_assessment import ImpactAssessmentDB
from app.db.models.report import ReportDB
from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.models.evidence import EvidenceSourceType
from app.models.evidence_mapping import EvidenceRelevance
from app.models.goal import GoalStatus
from app.models.impact_assessment import ImpactType
from app.models.report import ReportStatus, ReportType
from app.repositories.evidence import EvidenceRepository
from app.repositories.evidence_mapping import EvidenceMappingRepository
from app.repositories.evidence_version import EvidenceVersionRepository
from app.repositories.goal import GoalRepository
from app.repositories.impact_assessment import ImpactAssessmentRepository
from app.repositories.report import ReportRepository
from app.repositories.user import UserRepository


@pytest.mark.integration
def test_complete_repository_workflow():
    session = SessionLocal()

    user_id = f"workflow-user-{uuid4()}"
    goal_id = f"workflow-goal-{uuid4()}"
    evidence_id = f"workflow-evidence-{uuid4()}"
    version_id = f"workflow-version-{uuid4()}"
    mapping_id = f"workflow-mapping-{uuid4()}"
    assessment_id = f"workflow-assessment-{uuid4()}"
    report_id = f"workflow-report-{uuid4()}"

    try:
        # ---------------------------------------------------------
        # 1. Create User
        # ---------------------------------------------------------
        user_repository = UserRepository(session)

        user_repository.create(
            user_id=user_id,
            name="Repository Workflow User",
            email=f"{uuid4()}@example.com",
            role="Engineer",
        )

        session.commit()

        retrieved_user = user_repository.get_by_id(user_id)

        assert retrieved_user is not None
        assert retrieved_user.id == user_id
        assert retrieved_user.name == "Repository Workflow User"

        # ---------------------------------------------------------
        # 2. Create Goal
        # ---------------------------------------------------------
        goal_repository = GoalRepository(session)

        goal_repository.create(
            goal_id=goal_id,
            user_id=user_id,
            title="Improve deployment reliability",
            description="Improve deployment monitoring and reliability.",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            status=GoalStatus.ACTIVE,
            source="performance_plan",
        )

        session.commit()

        retrieved_goal = goal_repository.get_by_id(goal_id)

        assert retrieved_goal is not None
        assert retrieved_goal.id == goal_id
        assert retrieved_goal.user_id == user_id
        assert retrieved_goal.title == "Improve deployment reliability"
        assert retrieved_goal.status == GoalStatus.ACTIVE

        # ---------------------------------------------------------
        # 3. Create Evidence
        # ---------------------------------------------------------
        evidence_repository = EvidenceRepository(session)

        captured_at = datetime.now(UTC)

        evidence_repository.create(
            evidence_id=evidence_id,
            user_id=user_id,
            source_type=EvidenceSourceType.JIRA,
            source_id="PROJ-123",
            title="Implemented deployment monitoring",
            description=(
                "Implemented CPU, memory, and restart monitoring "
                "for deployment services."
            ),
            source_url="https://example.com/PROJ-123",
            captured_at=captured_at,
            source_updated_at=captured_at,
            content_hash="workflow-hash-v1",
        )

        session.commit()

        retrieved_evidence = evidence_repository.get_by_id(evidence_id)

        assert retrieved_evidence is not None
        assert retrieved_evidence.id == evidence_id
        assert retrieved_evidence.user_id == user_id
        assert retrieved_evidence.source_type == EvidenceSourceType.JIRA
        assert retrieved_evidence.source_id == "PROJ-123"
        assert retrieved_evidence.title == "Implemented deployment monitoring"

        # ---------------------------------------------------------
        # 4. Create Evidence Version
        # ---------------------------------------------------------
        version_repository = EvidenceVersionRepository(session)

        version_repository.create(
            version_id=version_id,
            evidence_id=evidence_id,
            version=1,
            content=(
                "Implemented CPU, memory, and restart monitoring "
                "for deployment services."
            ),
            content_hash="workflow-content-hash-v1",
            captured_at=captured_at,
            source_updated_at=captured_at,
        )

        session.commit()

        retrieved_version = version_repository.get_by_id(version_id)

        assert retrieved_version is not None
        assert retrieved_version.id == version_id
        assert retrieved_version.evidence_id == evidence_id
        assert retrieved_version.version == 1
        assert retrieved_version.content_hash == "workflow-content-hash-v1"

        # ---------------------------------------------------------
        # 5. Create Evidence → Goal Mapping
        # ---------------------------------------------------------
        mapping_repository = EvidenceMappingRepository(session)

        mapping_repository.create(
            mapping_id=mapping_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            relevance=EvidenceRelevance.HIGH,
            confidence=0.95,
            reason=(
                "Deployment monitoring directly supports the "
                "deployment reliability goal."
            ),
        )

        session.commit()

        retrieved_mapping = mapping_repository.get_by_id(mapping_id)

        assert retrieved_mapping is not None
        assert retrieved_mapping.id == mapping_id
        assert retrieved_mapping.evidence_id == evidence_id
        assert retrieved_mapping.goal_id == goal_id
        assert retrieved_mapping.relevance == EvidenceRelevance.HIGH
        assert retrieved_mapping.confidence == 0.95

        # ---------------------------------------------------------
        # 6. Create Impact Assessment
        # ---------------------------------------------------------
        assessment_repository = ImpactAssessmentRepository(session)

        assessment_repository.create(
            assessment_id=assessment_id,
            evidence_id=evidence_id,
            goal_id=goal_id,
            impact_type=ImpactType.RELIABILITY,
            impact_summary=(
                "Improved deployment reliability by introducing "
                "proactive monitoring for critical service conditions."
            ),
            impact_score=0.90,
            confidence=0.92,
            assessment_version=1,
        )

        session.commit()

        retrieved_assessment = assessment_repository.get_by_id(assessment_id)

        assert retrieved_assessment is not None
        assert retrieved_assessment.id == assessment_id
        assert retrieved_assessment.evidence_id == evidence_id
        assert retrieved_assessment.goal_id == goal_id
        assert retrieved_assessment.impact_type == ImpactType.RELIABILITY
        assert retrieved_assessment.impact_score == 0.90
        assert retrieved_assessment.confidence == 0.92
        assert retrieved_assessment.assessment_version == 1

        # ---------------------------------------------------------
        # 7. Create Report
        # ---------------------------------------------------------
        report_repository = ReportRepository(session)

        report_repository.create(
            report_id=report_id,
            user_id=user_id,
            report_type=ReportType.MONTHLY_IMPACT,
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            content=(
                "September impact report: improved deployment "
                "reliability through proactive monitoring."
            ),
            version=1,
            status=ReportStatus.CURRENT,
        )

        session.commit()

        retrieved_report = report_repository.get_by_id(report_id)

        assert retrieved_report is not None
        assert retrieved_report.id == report_id
        assert retrieved_report.user_id == user_id
        assert retrieved_report.report_type == ReportType.MONTHLY_IMPACT
        assert retrieved_report.version == 1
        assert retrieved_report.status == ReportStatus.CURRENT

        # ---------------------------------------------------------
        # 8. Verify repository-level relationships
        # ---------------------------------------------------------
        user_goals = goal_repository.get_by_user_id(user_id)

        assert len(user_goals) == 1
        assert user_goals[0].id == goal_id

        user_evidence = evidence_repository.get_by_user_id(user_id)

        assert len(user_evidence) == 1
        assert user_evidence[0].id == evidence_id

        evidence_versions = version_repository.get_by_evidence_id(
            evidence_id
        )

        assert len(evidence_versions) == 1
        assert evidence_versions[0].id == version_id

        evidence_mappings = mapping_repository.get_by_evidence_id(
            evidence_id
        )

        assert len(evidence_mappings) == 1
        assert evidence_mappings[0].goal_id == goal_id

        goal_mappings = mapping_repository.get_by_goal_id(goal_id)

        assert len(goal_mappings) == 1
        assert goal_mappings[0].evidence_id == evidence_id

        evidence_assessments = (
            assessment_repository.get_by_evidence_id(evidence_id)
        )

        assert len(evidence_assessments) == 1
        assert evidence_assessments[0].id == assessment_id

        goal_assessments = assessment_repository.get_by_goal_id(goal_id)

        assert len(goal_assessments) == 1
        assert goal_assessments[0].evidence_id == evidence_id

        user_reports = report_repository.get_by_user_id(user_id)

        assert len(user_reports) == 1
        assert user_reports[0].id == report_id

        period_report = report_repository.get_by_user_id_and_period(
            user_id,
            date(2026, 9, 1),
            date(2026, 9, 30),
        )

        assert period_report is not None
        assert period_report.id == report_id

    finally:
        # Delete in dependency order.
        session.execute(
            delete(ReportDB).where(ReportDB.id == report_id)
        )
        session.execute(
            delete(ImpactAssessmentDB).where(
                ImpactAssessmentDB.id == assessment_id
            )
        )
        session.execute(
            delete(EvidenceMappingDB).where(
                EvidenceMappingDB.id == mapping_id
            )
        )
        session.execute(
            delete(EvidenceVersionDB).where(
                EvidenceVersionDB.id == version_id
            )
        )
        session.execute(
            delete(EvidenceDB).where(EvidenceDB.id == evidence_id)
        )
        session.execute(
            delete(GoalDB).where(GoalDB.id == goal_id)
        )
        session.execute(
            delete(UserDB).where(UserDB.id == user_id)
        )

        session.commit()
        session.close()