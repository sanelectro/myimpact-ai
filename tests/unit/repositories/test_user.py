from datetime import UTC, datetime
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.db.models.user import UserDB
from app.repositories.user import UserRepository
from app.utils.email import normalize_email


def test_get_by_id_returns_user():
    session = MagicMock(spec=Session)
    expected_user = UserDB(
        id="user-1",
        name="Test User",
        email="test@example.com",
        role="Engineer",
    )

    session.get.return_value = expected_user

    repository = UserRepository(session)

    result = repository.get_by_id("user-1")

    assert result is expected_user
    session.get.assert_called_once_with(UserDB, "user-1")
    
def test_get_by_id_returns_none_when_user_not_found():
    session = MagicMock(spec=Session)
    session.get.return_value = None

    repository = UserRepository(session)

    result = repository.get_by_id("missing-user")

    assert result is None
    session.get.assert_called_once_with(UserDB, "missing-user")
    
def test_get_by_email_returns_user():
    session = MagicMock(spec=Session)
    expected_user = UserDB(
        id="user-1",
        name="Test User",
        email="test@example.com",
        role="Engineer",
    )

    session.query.return_value.filter.return_value.first.return_value = expected_user

    repository = UserRepository(session)

    result = repository.get_by_email("TEST@EXAMPLE.COM")

    assert result is expected_user
    
def test_get_by_email_returns_none_when_user_not_found():
    session = MagicMock(spec=Session)

    session.query.return_value.filter.return_value.first.return_value = None

    repository = UserRepository(session)

    result = repository.get_by_email("missing@example.com")

    assert result is None
    
def test_normalize_email_strips_whitespace_and_lowercases():
    result = normalize_email("  TEST@Example.COM  ")

    assert result == "test@example.com"
    
def test_create_user():
    session = MagicMock(spec=Session)

    repository = UserRepository(session)

    result = repository.create(
        user_id="user-1",
        name="Test User",
        email="  TEST@EXAMPLE.COM  ",
        role="Engineer",
    )

    assert isinstance(result, UserDB)
    assert result.id == "user-1"
    assert result.name == "Test User"
    assert result.email == "test@example.com"
    assert result.role == "Engineer"
    assert isinstance(result.created_at, datetime)
    assert result.created_at.tzinfo == UTC
    assert result.updated_at == result.created_at

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once()