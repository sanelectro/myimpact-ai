from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.threshold_governance import (
    ThresholdApprovalDB,
    ThresholdAuditEventDB,
    ThresholdItemDB,
    ThresholdSetDB,
)
from app.evaluation.evaluation_metrics import (
    METRIC_DEFINITIONS_BY_ID,
    get_metric_definition,
)
from app.models.threshold_governance import (
    ThresholdDecision,
    ThresholdOperator,
    ThresholdSetStatus,
)

REQUIRED_METRIC_IDS = tuple(METRIC_DEFINITIONS_BY_ID)


class ThresholdValidationError(ValueError):
    """Raised when a threshold-set governance rule is violated."""


def create_threshold_set(
    db: Session,
    *,
    name: str,
    dataset_id: str,
    dataset_version: str,
    prompt_version: str,
    model_identifier: str,
    model_configuration: dict,
    evaluation_code_version: str,
    created_by_user_id: str,
    proposal_rationale: str,
    items: list[dict],
    threshold_set_id: str | None = None,
    version: int = 1,
    created_at: datetime | None = None,
) -> ThresholdSetDB:
    if not proposal_rationale.strip():
        raise ThresholdValidationError("Proposal rationale is required.")
    if version < 1:
        raise ThresholdValidationError("Threshold-set version must be positive.")
    if not items:
        raise ThresholdValidationError("A threshold set requires metric items.")
    _validate_items(items)

    now = created_at or datetime.now(UTC)
    threshold_set = ThresholdSetDB(
        id=threshold_set_id or str(uuid4()),
        version=version,
        name=name.strip(),
        status=ThresholdSetStatus.DRAFT,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        prompt_version=prompt_version,
        model_identifier=model_identifier,
        model_configuration=model_configuration,
        evaluation_code_version=evaluation_code_version,
        created_by_user_id=created_by_user_id,
        created_at=now,
        proposal_rationale=proposal_rationale.strip(),
    )
    db.add(threshold_set)
    for item in items:
        db.add(
            ThresholdItemDB(
                id=str(uuid4()),
                threshold_set_id=threshold_set.id,
                metric_id=item["metric_id"],
                metric_definition_version=item["metric_definition_version"],
                operator=item["operator"],
                threshold_value=Decimal(str(item["threshold_value"])),
                unit=item["unit"],
                rationale=item["rationale"].strip(),
                required=item.get("required", True),
            )
        )
    _audit(
        db,
        threshold_set=threshold_set,
        actor_user_id=created_by_user_id,
        event_type="THRESHOLD_SET_CREATED",
        entity_id=threshold_set.id,
        details={"item_count": len(items)},
        created_at=now,
    )
    db.commit()
    db.refresh(threshold_set)
    return threshold_set


def propose_threshold_set(
    db: Session,
    *,
    threshold_set_id: str,
    actor_user_id: str,
    proposed_at: datetime | None = None,
) -> ThresholdSetDB:
    threshold_set = _get_threshold_set(db, threshold_set_id)
    if threshold_set.status != ThresholdSetStatus.DRAFT:
        raise ThresholdValidationError("Only a draft threshold set can be proposed.")
    _validate_persisted_items(threshold_set.items)
    now = proposed_at or datetime.now(UTC)
    threshold_set.status = ThresholdSetStatus.PROPOSED
    _audit(
        db,
        threshold_set=threshold_set,
        actor_user_id=actor_user_id,
        event_type="THRESHOLD_SET_PROPOSED",
        entity_id=threshold_set.id,
        details={"version": threshold_set.version},
        created_at=now,
    )
    db.commit()
    db.refresh(threshold_set)
    return threshold_set


def decide_threshold_set(
    db: Session,
    *,
    threshold_set_id: str,
    approver_user_id: str,
    decision: ThresholdDecision,
    rationale: str,
    authorized: bool,
    decided_at: datetime | None = None,
    policy_reference: str | None = None,
) -> ThresholdApprovalDB:
    if not authorized:
        raise ThresholdValidationError("The user is not authorized to decide thresholds.")
    if not rationale.strip():
        raise ThresholdValidationError("Approval or rejection rationale is required.")
    threshold_set = _get_threshold_set(db, threshold_set_id)
    if threshold_set.status != ThresholdSetStatus.PROPOSED:
        raise ThresholdValidationError("Only a proposed threshold set can be decided.")
    if threshold_set.created_by_user_id == approver_user_id:
        raise ThresholdValidationError("The proposal creator cannot approve its own set.")
    _validate_persisted_items(threshold_set.items)
    now = decided_at or datetime.now(UTC)
    approval = ThresholdApprovalDB(
        id=str(uuid4()),
        threshold_set_id=threshold_set.id,
        threshold_set_version=threshold_set.version,
        decision=decision,
        approver_user_id=approver_user_id,
        decided_at=now,
        rationale=rationale.strip(),
        policy_reference=policy_reference,
    )
    threshold_set.status = (
        ThresholdSetStatus.APPROVED
        if decision == ThresholdDecision.APPROVED
        else ThresholdSetStatus.REJECTED
    )
    db.add(approval)
    _audit(
        db,
        threshold_set=threshold_set,
        actor_user_id=approver_user_id,
        event_type=f"THRESHOLD_SET_{decision.value}",
        entity_id=approval.id,
        details={"version": threshold_set.version},
        created_at=now,
    )
    db.commit()
    db.refresh(approval)
    return approval


def _validate_items(items: list[dict]) -> None:
    metric_ids = [item.get("metric_id") for item in items]
    if len(metric_ids) != len(set(metric_ids)):
        raise ThresholdValidationError("A metric may appear only once in a threshold set.")
    missing = set(REQUIRED_METRIC_IDS) - set(metric_ids)
    if missing:
        raise ThresholdValidationError(
            f"Threshold set is missing required metrics: {', '.join(sorted(missing))}."
        )
    for item in items:
        metric_id = item.get("metric_id")
        definition = get_metric_definition(metric_id)
        if item.get("metric_definition_version") != definition.definition_version:
            raise ThresholdValidationError(
                f"Metric definition version mismatch for {metric_id}."
            )
        if item.get("unit") != definition.unit.value:
            raise ThresholdValidationError(f"Metric unit mismatch for {metric_id}.")
        operator = item.get("operator")
        if isinstance(operator, ThresholdOperator):
            operator = operator.value
        if operator not in {operator.value for operator in ThresholdOperator}:
            raise ThresholdValidationError(f"Unsupported threshold operator for {metric_id}.")
        if (
            definition.direction.value == "HIGHER_IS_BETTER"
            and operator != ThresholdOperator.GREATER_THAN_OR_EQUAL.value
        ) or (
            definition.direction.value == "LOWER_IS_BETTER"
            and operator != ThresholdOperator.LESS_THAN_OR_EQUAL.value
        ):
            raise ThresholdValidationError(
                f"Threshold operator is incompatible with {metric_id} direction."
            )
        value = item.get("threshold_value")
        if not isinstance(value, (int, float, Decimal)) or not 0 <= float(value) <= 1:
            raise ThresholdValidationError(
                f"Threshold value for {metric_id} must be between 0 and 1."
            )
        if not isinstance(item.get("rationale"), str) or not item["rationale"].strip():
            raise ThresholdValidationError(f"Threshold rationale is required for {metric_id}.")


def _validate_persisted_items(items: list[ThresholdItemDB]) -> None:
    _validate_items(
        [
            {
                "metric_id": item.metric_id,
                "metric_definition_version": item.metric_definition_version,
                "operator": (
                    item.operator.value
                    if isinstance(item.operator, ThresholdOperator)
                    else item.operator
                ),
                "threshold_value": item.threshold_value,
                "unit": item.unit,
                "rationale": item.rationale,
                "required": item.required,
            }
            for item in items
        ]
    )


def _get_threshold_set(db: Session, threshold_set_id: str) -> ThresholdSetDB:
    threshold_set = db.scalar(
        select(ThresholdSetDB).where(ThresholdSetDB.id == threshold_set_id)
    )
    if threshold_set is None:
        raise ThresholdValidationError("Threshold set was not found.")
    return threshold_set


def _audit(
    db: Session,
    *,
    threshold_set: ThresholdSetDB,
    actor_user_id: str,
    event_type: str,
    entity_id: str,
    details: dict[str, object],
    created_at: datetime,
) -> None:
    db.add(
        ThresholdAuditEventDB(
            id=str(uuid4()),
            threshold_set_id=threshold_set.id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            entity_id=entity_id,
            details=details,
            created_at=created_at,
        )
    )
