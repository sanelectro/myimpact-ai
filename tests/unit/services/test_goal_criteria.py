import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import Column, String, Table, create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
import app.db.models
from app.db.models.goal import GoalDB
from app.db.models.goal_criterion import GoalCriterionDB, GoalCriterionVersionDB
from app.db.models.user import UserDB
from app.models.goal import GoalScope, GoalStatus, GoalSubStatus
from app.models.goal_criteria import (
    GoalCriterionApprovalStatus,
    GoalCriterionDefinition,
    GoalCriterionType,
    GoalCriterionUpdateRequest,
)
from app.models.llm import LLMResponse
from app.services.goal_criteria import GoalCriteriaService


def test_adding_a_criterion_version_obsoletes_previous_assessments():
    session = Mock()
    service = GoalCriteriaService(session)
    criterion = SimpleNamespace(
        id="criterion-1",
        current_version=1,
        is_retired=False,
    )
    service.repository.get_by_id_and_goal = Mock(return_value=criterion)
    service.repository.add_version = Mock()
    service.repository.get_by_id = Mock(return_value=criterion)
    service._obsolete_assessments = Mock()
    request = GoalCriterionUpdateRequest(
        definition=GoalCriterionDefinition(
            criterion_type=GoalCriterionType.BINARY,
            description="Complete the deployment migration",
            completion_conditions="The production deployment is complete.",
        )
    )

    result = service.add_version(
        "goal-1",
        "criterion-1",
        "user-1",
        request,
    )

    assert result[0] is criterion
    service._obsolete_assessments.assert_called_once_with(
        "criterion-1",
        "Criterion definition edited",
    )


def test_generation_persists_proposed_criteria_for_a_goal():
    assert app.db.models.GoalDB is GoalDB
    teams = Base.metadata.tables.get("teams")
    created_teams_table = teams is None
    if teams is None:
        teams = Table("teams", Base.metadata, Column("id", String(64), primary_key=True))

    engine = create_engine("sqlite://")
    now = datetime.now(UTC)
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                teams,
                UserDB.__table__,
                GoalDB.__table__,
                GoalCriterionDB.__table__,
                GoalCriterionVersionDB.__table__,
            ],
        )
        with Session(engine) as session:
            user = UserDB(
                id="synthetic-user",
                name="Test User",
                email="synthetic@example.test",
                created_at=now,
                updated_at=now,
            )
            goal = GoalDB(
                id="synthetic-goal",
                user_id=user.id,
                title="Improve deployment reliability",
                description="Reduce failed releases through safer rollout practices.",
                scope=GoalScope.PERSONAL,
                status=GoalStatus.DRAFT,
                sub_status=GoalSubStatus.NEEDS_REVIEW,
                created_at=now,
                updated_at=now,
            )
            session.add_all([user, goal])
            session.commit()

            class SyntheticLLM:
                async def generate(self, _request):
                    assert _request.response_format == {"type": "json_object"}
                    return LLMResponse(
                        model="synthetic-test-model",
                        content=json.dumps(
                            {
                                "criteria": [
                                    {
                                        "criterion_type": "BINARY",
                                        "description": "Enable production canary validation",
                                        "completion_conditions": "Canary validation is enabled and verified in production.",
                                        "milestones": [],
                                        "target_value": None,
                                        "unit": None,
                                        "evidence_suggestions": ["Deployment configuration"],
                                        "assumptions_and_clarifications": [],
                                    },
                                    {
                                        "criterion_type": "MEASURABLE_TARGET",
                                        "description": "Reduce failed production releases by 20 percent",
                                        "completion_conditions": "The measured failure rate decreases by at least 20 percent.",
                                        "milestones": [],
                                        "target_value": 20,
                                        "unit": "percent",
                                        "evidence_suggestions": ["Release metrics"],
                                        "assumptions_and_clarifications": [],
                                    },
                                ]
                            }
                        ),
                    )

            generated = asyncio.run(
                GoalCriteriaService(session, SyntheticLLM()).generate(goal, user.id)
            )

            assert len(generated) == 2
            assert all(item.current_version is None for item in generated)
            assert all(
                item.versions[0].approval_status == GoalCriterionApprovalStatus.PROPOSED
                for item in generated
            )
            assert all(
                item.versions[0].model_version == "synthetic-test-model"
                for item in generated
            )
    finally:
        engine.dispose()
        if created_teams_table and teams is not None:
            Base.metadata.remove(teams)
