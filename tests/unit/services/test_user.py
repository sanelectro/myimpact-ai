from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.user import UserDB
from app.exceptions import UserAlreadyExistsError
from app.models.user import UserCreate
from app.repositories.user import UserRepository
from app.services.user import UserService


def test_create_user():
    session = MagicMock(spec=Session)
    user_data = UserCreate(
        name="Test User",
        email="test@example.com",
        role="Engineer",
    )

    expected_user = MagicMock(spec=UserDB)

    with patch(
        "app.services.user.uuid4",
        return_value="user-123",
    ):
        repository = MagicMock(spec=UserRepository)
        repository.create.return_value = expected_user

        service = UserService(session)
        service.repository = repository

        result = service.create_user(user_data)

    assert result is expected_user

    repository.create.assert_called_once_with(
        user_id="user-123",
        name="Test User",
        email="test@example.com",
        role="Engineer",
    )

    session.commit.assert_called_once()
    
    
def test_get_user_by_id():
    session = MagicMock(spec=Session)
    expected_user = MagicMock(spec=UserDB)

    repository = MagicMock(spec=UserRepository)
    repository.get_by_id.return_value = expected_user

    service = UserService(session)
    service.repository = repository

    result = service.get_user_by_id("user-123")

    assert result is expected_user
    repository.get_by_id.assert_called_once_with("user-123")
    session.commit.assert_not_called()
    
    
def test_get_user_by_email():
    session = MagicMock(spec=Session)
    expected_user = MagicMock(spec=UserDB)

    repository = MagicMock(spec=UserRepository)
    repository.get_by_email.return_value = expected_user

    service = UserService(session)
    service.repository = repository

    result = service.get_user_by_email("TEST@EXAMPLE.COM")

    assert result is expected_user
    repository.get_by_email.assert_called_once_with("TEST@EXAMPLE.COM")
    session.commit.assert_not_called()
    
    
def test_get_user_by_id_returns_none():
    session = MagicMock(spec=Session)

    repository = MagicMock(spec=UserRepository)
    repository.get_by_id.return_value = None

    service = UserService(session)
    service.repository = repository

    result = service.get_user_by_id("missing-user")

    assert result is None
    repository.get_by_id.assert_called_once_with("missing-user")
    session.commit.assert_not_called()
    
    
def test_get_user_by_email_returns_none():
    session = MagicMock(spec=Session)

    repository = MagicMock(spec=UserRepository)
    repository.get_by_email.return_value = None

    service = UserService(session)
    service.repository = repository

    result = service.get_user_by_email("missing@example.com")

    assert result is None
    repository.get_by_email.assert_called_once_with(
        "missing@example.com"
    )
    session.commit.assert_not_called()
    
    
    
def test_create_user_raises_user_already_exists_on_duplicate_email():
    session = MagicMock(spec=Session)

    user_data = UserCreate(
        name="Duplicate User",
        email="duplicate@example.com",
        role="Engineer",
    )

    repository = MagicMock(spec=UserRepository)

    database_error = MagicMock()
    database_error.diag.constraint_name = "ix_users_email"

    integrity_error = IntegrityError(
        "duplicate",
        {},
        database_error,
    )

    repository.create.side_effect = integrity_error

    service = UserService(session)
    service.repository = repository

    with pytest.raises(
        UserAlreadyExistsError,
        match="A user with this email already exists.",
    ):
        service.create_user(user_data)

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    
    
    
def test_create_user_reraises_other_integrity_error():
    session = MagicMock(spec=Session)

    user_data = UserCreate(
        name="Test User",
        email="test@example.com",
        role="Engineer",
    )

    repository = MagicMock(spec=UserRepository)

    database_error = MagicMock()
    database_error.diag.constraint_name = "some_other_constraint"

    integrity_error = IntegrityError(
        "constraint violation",
        {},
        database_error,
    )

    repository.create.side_effect = integrity_error

    service = UserService(session)
    service.repository = repository

    with pytest.raises(IntegrityError):
        service.create_user(user_data)

    session.rollback.assert_called_once()
    session.commit.assert_not_called()