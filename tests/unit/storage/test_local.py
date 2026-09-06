from pathlib import Path

import pytest

from app.storage.local import LocalFileStorage, StorageFileNotFoundError


def test_save_and_read_file(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    storage_path = storage.save(
        user_id="user-1",
        document_id="document-1",
        file_name="goals.pdf",
        content=b"goal content",
    )

    assert storage_path == str(
        tmp_path / "user-1" / "document-1" / "goals.pdf"
    )
    assert storage.read(storage_path) == b"goal content"


def test_save_creates_user_and_document_directories(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    storage_path = storage.save(
        user_id="user-1",
        document_id="document-1",
        file_name="role.docx",
        content=b"role content",
    )

    assert Path(storage_path).is_file()
    assert Path(storage_path).parent == (
        tmp_path / "user-1" / "document-1"
    )


def test_exists_returns_true_for_existing_file(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    storage_path = storage.save(
        user_id="user-1",
        document_id="document-1",
        file_name="one-to-one.docx",
        content=b"one-to-one",
    )

    assert storage.exists(storage_path) is True


def test_exists_returns_false_for_missing_file(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    assert storage.exists(str(tmp_path / "missing.txt")) is False


def test_read_missing_file_raises(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(StorageFileNotFoundError):
        storage.read(str(tmp_path / "missing.txt"))


def test_delete_file(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    storage_path = storage.save(
        user_id="user-1",
        document_id="document-1",
        file_name="evidence.pdf",
        content=b"evidence",
    )

    storage.delete(storage_path)

    assert storage.exists(storage_path) is False


def test_delete_missing_file_raises(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(StorageFileNotFoundError):
        storage.delete(str(tmp_path / "missing.txt"))


def test_files_are_isolated_by_user_and_document(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    user_one_path = storage.save(
        user_id="user-1",
        document_id="document-1",
        file_name="same.pdf",
        content=b"user one",
    )

    user_two_path = storage.save(
        user_id="user-2",
        document_id="document-1",
        file_name="same.pdf",
        content=b"user two",
    )

    assert user_one_path != user_two_path
    assert storage.read(user_one_path) == b"user one"
    assert storage.read(user_two_path) == b"user two"


def test_document_isolation_for_same_user(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    first_path = storage.save(
        user_id="user-1",
        document_id="document-1",
        file_name="file.pdf",
        content=b"first",
    )

    second_path = storage.save(
        user_id="user-1",
        document_id="document-2",
        file_name="file.pdf",
        content=b"second",
    )

    assert first_path != second_path
    assert storage.read(first_path) == b"first"
    assert storage.read(second_path) == b"second"


def test_rejects_path_traversal_in_user_id(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.save(
            user_id="../other-user",
            document_id="document-1",
            file_name="file.pdf",
            content=b"data",
        )


def test_rejects_path_traversal_in_document_id(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.save(
            user_id="user-1",
            document_id="../document-1",
            file_name="file.pdf",
            content=b"data",
        )


def test_rejects_directory_segments_in_file_name(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.save(
            user_id="user-1",
            document_id="document-1",
            file_name="../file.pdf",
            content=b"data",
        )


def test_read_rejects_path_outside_storage_root(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"secret")

    with pytest.raises(ValueError):
        storage.read(str(outside))
