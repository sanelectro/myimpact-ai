from pathlib import Path

from app.exceptions import StorageFileNotFoundError
from app.storage.interface import FileStorage


class LocalFileStorage(FileStorage):
    """Filesystem-backed storage implementation for local development."""

    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path).expanduser().resolve()
        self.root_path.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        *,
        user_id: str,
        document_id: str,
        file_name: str,
        content: bytes,
    ) -> str:
        safe_user_id = self._validate_path_part(user_id, "user_id")
        safe_document_id = self._validate_path_part(
            document_id,
            "document_id",
        )
        safe_file_name = self._validate_file_name(file_name)

        target = (
            self.root_path
            / safe_user_id
            / safe_document_id
            / safe_file_name
        )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        return str(target)

    def read(self, storage_path: str) -> bytes:
        target = self._resolve_existing_path(storage_path)
        if not target.is_file():
            raise StorageFileNotFoundError(storage_path)

        return target.read_bytes()

    def delete(self, storage_path: str) -> None:
        target = self._resolve_existing_path(storage_path)
        if not target.is_file():
            raise StorageFileNotFoundError(storage_path)

        target.unlink()

    def exists(self, storage_path: str) -> bool:
        try:
            target = self._resolve_existing_path(storage_path)
        except ValueError:
            return False

        return target.is_file()

    def _resolve_existing_path(self, storage_path: str) -> Path:
        candidate = Path(storage_path).expanduser()

        if not candidate.is_absolute():
            candidate = self.root_path / candidate

        resolved = candidate.resolve()

        try:
            resolved.relative_to(self.root_path)
        except ValueError as exc:
            raise ValueError("Storage path escapes the storage root") from exc

        return resolved

    @staticmethod
    def _validate_path_part(value: str, field_name: str) -> str:
        if not value or value in {".", ".."}:
            raise ValueError(f"Invalid {field_name}")

        path = Path(value)
        if len(path.parts) != 1:
            raise ValueError(f"Invalid {field_name}")

        return value

    @staticmethod
    def _validate_file_name(file_name: str) -> str:
        if not file_name or file_name in {".", ".."}:
            raise ValueError("Invalid file_name")

        # Store only the filename component. Any supplied directory
        # segments are rejected instead of silently rewritten.
        path = Path(file_name)
        if len(path.parts) != 1:
            raise ValueError("file_name must not contain directory segments")

        if path.name != file_name:
            raise ValueError("Invalid file_name")

        return file_name
