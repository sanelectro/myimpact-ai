from sqlalchemy.orm import Session

from app.db.models.goal_validation_run import GoalValidationRunDB


class GoalValidationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, run: GoalValidationRunDB) -> GoalValidationRunDB:
        self.session.add(run)
        self.session.flush()
        return run

    def list_for_goal(self, goal_id: str) -> list[GoalValidationRunDB]:
        return (
            self.session.query(GoalValidationRunDB)
            .filter(GoalValidationRunDB.goal_id == goal_id)
            .order_by(
                GoalValidationRunDB.created_at.desc(),
                GoalValidationRunDB.id.desc(),
            )
            .all()
        )
