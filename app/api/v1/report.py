from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.evidence import get_goal_service
from app.api.v1.insight import get_career_insight_service, get_impact_assessment_service
from app.db.session import get_db
from app.exceptions import ImpactAssessmentEvaluationError
from app.models.api_v1_insight import GoalReportResponse
from app.models.goal import Goal
from app.models.impact_assessment import ImpactAssessment
from app.services.goal import GoalService
from app.services.impact_assessment import ImpactAssessmentService
from app.services.knowledge.career_insight import CareerInsightService

router = APIRouter(prefix="/goals", tags=["goal-report"])


def _require_goal(goal, user_id: str):
    if goal is None or goal.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    return goal


@router.get("/{goal_id}/report", response_model=GoalReportResponse)
async def get_goal_report(
    goal_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    goal_service: Annotated[GoalService, Depends(get_goal_service)],
    impact_service: Annotated[
        ImpactAssessmentService,
        Depends(get_impact_assessment_service),
    ],
    insight_service: Annotated[
        CareerInsightService,
        Depends(get_career_insight_service),
    ],
) -> GoalReportResponse:
    goal_db = _require_goal(goal_service.get_goal_by_id(goal_id), user_id)
    assessments = [
        ImpactAssessment.model_validate(item, from_attributes=True)
        for item in impact_service.get_assessments_by_goal_id(goal_id)
    ]
    goal = Goal.model_validate(goal_db, from_attributes=True)

    if not assessments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Goal has no impact assessments",
        )

    try:
        insight = await insight_service.synthesize(goal, assessments)
    except ImpactAssessmentEvaluationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return GoalReportResponse(
        goal_id=goal.id,
        goal_title=goal.title,
        generated_at=datetime.now(UTC),
        headline=insight.headline,
        summary=insight.summary,
        impact_types=insight.impact_types,
        supporting_assessment_ids=insight.supporting_assessment_ids,
        confidence=insight.confidence,
        impact_assessment_count=len(assessments),
    )
