class UserAlreadyExistsError(Exception):
    """Raised when a user with the same email already exists."""


class EvidenceMappingAlreadyExistsError(Exception):
    """Raised when an evidence-to-goal mapping already exists."""