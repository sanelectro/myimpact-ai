from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.repositories.user import UserRepository


@pytest.mark.integration
def test_create_and_get_user():
    user_id = f"test-{uuid4()}"

    session = SessionLocal()

    try:
        repository = UserRepository(session)

        created_user = repository.create(
            user_id=user_id,
            name="Integration Test User",
            email=f"  TEST-{uuid4()}@EXAMPLE.COM  ",
            role="Engineer",
        )

        session.commit()

        assert created_user.id == user_id
        assert created_user.email.startswith("test-")
        assert created_user.email.endswith("@example.com")

        user_by_id = repository.get_by_id(user_id)

        assert user_by_id is not None
        assert user_by_id.id == user_id

        user_by_email = repository.get_by_email(created_user.email.upper())

        assert user_by_email is not None
        assert user_by_email.id == user_id

    finally:
        session.execute(delete(UserDB).where(UserDB.id == user_id))
        session.commit()
        session.close()
        
        
        
@pytest.mark.integration
def test_create_user_rejects_duplicate_email():
    email = f"duplicate-{uuid4()}@example.com"
    first_user_id = f"test-{uuid4()}"
    second_user_id = f"test-{uuid4()}"

    session = SessionLocal()

    try:
        repository = UserRepository(session)

        repository.create(
            user_id=first_user_id,
            name="First User",
            email=email,
            role="Engineer",
        )
        session.commit()

        with pytest.raises(IntegrityError):
            repository.create(
                user_id=second_user_id,
                name="Second User",
                email=email.upper(),
                role="Engineer",
            )

        session.rollback()

    finally:
        session.execute(
            delete(UserDB).where(
                UserDB.id.in_([first_user_id, second_user_id])
            )
        )
        session.commit()
        session.close()