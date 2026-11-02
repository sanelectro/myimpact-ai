from enum import Enum


class ThresholdSetStatus(str, Enum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class ThresholdOperator(str, Enum):
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN_OR_EQUAL = "<="


class ThresholdDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
