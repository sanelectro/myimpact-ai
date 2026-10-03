from abc import ABC, abstractmethod


class FileStorage(ABC):
    """Abstract file storage contract for uploaded documents."""

    @abstractmethod
    def save(
        self,
        *,
        user_id: str,
        document_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        """Persist file content and return its storage path."""

    @abstractmethod
    def read(self, storage_path: str) -> bytes:
        """Read a previously stored file."""

    @abstractmethod
    def delete(self, storage_path: str) -> None:
        """Delete a previously stored file."""

    @abstractmethod
    def exists(self, storage_path: str) -> bool:
        """Return whether a stored file exists."""
