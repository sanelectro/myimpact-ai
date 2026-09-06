from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.services.base import BaseService


def test_base_service_accepts_session():
    session = MagicMock(spec=Session)

    service = BaseService(session)

    assert service.session is session


def test_commit_commits_session():
    session = MagicMock(spec=Session)

    service = BaseService(session)

    service.commit()

    session.commit.assert_called_once()


def test_rollback_rolls_back_session():
    session = MagicMock(spec=Session)

    service = BaseService(session)

    service.rollback()

    session.rollback.assert_called_once()