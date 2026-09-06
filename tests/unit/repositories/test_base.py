from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.repositories.base import BaseRepository


def test_base_repository_accepts_session():
    session = MagicMock(spec=Session)

    repository = BaseRepository(session)

    assert repository.session is session