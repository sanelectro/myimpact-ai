from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.threshold_governance import (
    MetricDefinitionDB,
    ThresholdApprovalDB,
    ThresholdAuditEventDB,
    ThresholdItemDB,
    ThresholdSetDB,
)
from app.db.models.organization import OrganizationDB
from app.db.models.team import TeamDB
from app.db.models.user import UserDB
from app.evaluation.evaluation_metrics import METRIC_DEFINITIONS
from app.models.threshold_governance import ThresholdDecision
from app.services.threshold_governance import (
    ThresholdValidationError,
    create_threshold_set,
    decide_threshold_set,
    propose_threshold_set,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        OrganizationDB.__table__,
        TeamDB.__table__,
        UserDB.__table__,
        MetricDefinitionDB.__table__,
        ThresholdSetDB.__table__,
        ThresholdItemDB.__table__,
        ThresholdApprovalDB.__table__,
        ThresholdAuditEventDB.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session


def _items():
    return [
        {
            "metric_id": definition.metric_id,
            "metric_definition_version": definition.definition_version,
            "operator": "<=" if definition.direction.value == "LOWER_IS_BETTER" else ">=",
            "threshold_value": 0.5,
            "unit": definition.unit.value,
            "rationale": f"Synthetic test rationale for {definition.metric_id}.",
        }
        for definition in METRIC_DEFINITIONS
    ]


def _create(db: Session):
    return create_threshold_set(
        db,
        name="Synthetic M6.6 test thresholds",
        dataset_id="dataset-v1",
        dataset_version="dataset-v1",
        prompt_version="prompt-v1",
        model_identifier="fixture-model",
        model_configuration={"temperature": 0},
        evaluation_code_version="test-code",
        created_by_user_id="creator",
        proposal_rationale="Synthetic test proposal; not an approval.",
        items=_items(),
        threshold_set_id="threshold-set-1",
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def test_incomplete_threshold_set_cannot_be_created(db: Session):
    items = _items()[:-1]

    with pytest.raises(ThresholdValidationError, match="missing required metrics"):
        create_threshold_set(
            db,
            name="Incomplete",
            dataset_id="dataset-v1",
            dataset_version="dataset-v1",
            prompt_version="prompt-v1",
            model_identifier="fixture-model",
            model_configuration={},
            evaluation_code_version="test-code",
            created_by_user_id="creator",
            proposal_rationale="Proposal rationale.",
            items=items,
        )


def test_threshold_proposal_and_approval_are_explicit_and_audited(db: Session):
    threshold_set = _create(db)
    proposed = propose_threshold_set(
        db,
        threshold_set_id=threshold_set.id,
        actor_user_id="creator",
    )

    assert proposed.status.value == "PROPOSED"
    with pytest.raises(ThresholdValidationError, match="cannot approve its own"):
        decide_threshold_set(
            db,
            threshold_set_id=threshold_set.id,
            approver_user_id="creator",
            decision=ThresholdDecision.APPROVED,
            rationale="Not allowed.",
            authorized=True,
        )

    approval = decide_threshold_set(
        db,
        threshold_set_id=threshold_set.id,
        approver_user_id="approver",
        decision=ThresholdDecision.APPROVED,
        rationale="Synthetic test approval.",
        authorized=True,
    )

    assert approval.decision.value == "APPROVED"
    assert db.get(ThresholdSetDB, threshold_set.id).status.value == "APPROVED"
    assert db.query(ThresholdAuditEventDB).count() == 3


def test_unauthorized_or_rationale_free_decisions_are_rejected(db: Session):
    threshold_set = _create(db)
    propose_threshold_set(db, threshold_set_id=threshold_set.id, actor_user_id="creator")

    with pytest.raises(ThresholdValidationError, match="not authorized"):
        decide_threshold_set(
            db,
            threshold_set_id=threshold_set.id,
            approver_user_id="approver",
            decision=ThresholdDecision.REJECTED,
            rationale="Rejected.",
            authorized=False,
        )
    with pytest.raises(ThresholdValidationError, match="rationale is required"):
        decide_threshold_set(
            db,
            threshold_set_id=threshold_set.id,
            approver_user_id="approver",
            decision=ThresholdDecision.REJECTED,
            rationale=" ",
            authorized=True,
        )


def test_approved_threshold_set_cannot_be_decided_twice(db: Session):
    threshold_set = _create(db)
    propose_threshold_set(db, threshold_set_id=threshold_set.id, actor_user_id="creator")
    decide_threshold_set(
        db,
        threshold_set_id=threshold_set.id,
        approver_user_id="approver",
        decision=ThresholdDecision.REJECTED,
        rationale="Synthetic rejection.",
        authorized=True,
    )

    with pytest.raises(ThresholdValidationError, match="Only a proposed"):
        decide_threshold_set(
            db,
            threshold_set_id=threshold_set.id,
            approver_user_id="second-approver",
            decision=ThresholdDecision.APPROVED,
            rationale="Too late.",
            authorized=True,
        )
