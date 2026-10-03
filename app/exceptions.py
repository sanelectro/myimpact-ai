class UserAlreadyExistsError(Exception):
    """Raised when a user with the same email already exists."""

class EvidenceMappingAlreadyExistsError(Exception):
    """Raised when an evidence-to-goal mapping already exists."""
    
class StorageFileNotFoundError(FileNotFoundError):
    """Raised when a requested stored file does not exist."""
    
class DocumentExtractionError(RuntimeError):
    """Raised when text cannot be extracted from a document."""


class DocumentClassificationError(RuntimeError):
    """Raised when a document cannot be classified safely."""


class DocumentExpectationExtractionError(RuntimeError):
    """Raised when structured expectations cannot be extracted safely."""

class DocumentChunkingError(Exception):
    """Raised when document content cannot be chunked."""