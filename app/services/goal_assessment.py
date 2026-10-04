from sqlalchemy.orm import Session

from app.models.api_v1_goals import GoalAssessmentResponse, GoalExpectationStatus
from app.repositories.evidence_mapping import EvidenceMappingRepository
from app.repositories.impact_assessment import ImpactAssessmentRepository
from app.services.base import BaseService


EXPECTED_ACHIEVEMENTS = 3


class GoalAssessmentService(BaseService):
    """Calculates the goal expectation state from persisted evidence and impact."""

    def __init__(self, session: Session):
        super().__init__(session)
        self.mapping_repository = EvidenceMappingRepository(session)
        self.impact_repository = ImpactAssessmentRepository(session)

    def assess(self, goal_id: str) -> GoalAssessmentResponse:
        mappings = self.mapping_repository.get_by_goal_id(goal_id)
        evidence_ids = {mapping.evidence_id for mapping in mappings}
        impact_evidence_ids = {
            assessment.evidence_id
            for assessment in self.impact_repository.get_by_goal_id(goal_id)
            if assessment.evidence_id in evidence_ids
        }

        achievement_count = len(evidence_ids)
        demonstrated_impact_count = len(impact_evidence_ids)
        qualifying_count = demonstrated_impact_count
        progress_percentage = round(
            qualifying_count / EXPECTED_ACHIEVEMENTS * 100
        )

        if achievement_count == 0:
            status = GoalExpectationStatus.NOT_STARTED
            description = (
                "You have not yet recorded a meaningful achievement for this goal. "
                "Start with one concrete contribution and capture the evidence and impact."
            )
        elif qualifying_count < EXPECTED_ACHIEVEMENTS:
            status = GoalExpectationStatus.IN_PROGRESS
            remaining = EXPECTED_ACHIEVEMENTS - qualifying_count
            if qualifying_count == 0:
                description = (
                    f"You have recorded {achievement_count} achievement{'' if achievement_count == 1 else 's'}, "
                    "but demonstrated impact is still missing. Keep building and connect measurable outcomes "
                    f"to reach the expected minimum of {EXPECTED_ACHIEVEMENTS}."
                )
            else:
                description = (
                    f"You have demonstrated {qualifying_count} meaningful achievement{'' if qualifying_count == 1 else 's'} "
                    f"with evidence and impact. {remaining} more {('achievement' if remaining == 1 else 'achievements')} "
                    "will meet the expected minimum."
                )
        elif qualifying_count == EXPECTED_ACHIEVEMENTS:
            status = GoalExpectationStatus.MET
            description = (
                f"You have demonstrated {qualifying_count} meaningful achievements, meeting the expected minimum of "
                f"{EXPECTED_ACHIEVEMENTS}."
            )
        else:
            status = GoalExpectationStatus.ABOVE
            description = (
                f"You have demonstrated {qualifying_count} meaningful achievements, exceeding the expected minimum of "
                f"{EXPECTED_ACHIEVEMENTS}."
            )

        return GoalAssessmentResponse(
            goal_id=goal_id,
            expected_achievement_count=EXPECTED_ACHIEVEMENTS,
            achievement_count=achievement_count,
            evidence_count=achievement_count,
            demonstrated_impact_count=demonstrated_impact_count,
            qualifying_achievement_count=qualifying_count,
            progress_percentage=progress_percentage,
            status=status,
            description=description,
        )
