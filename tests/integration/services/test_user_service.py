from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models.user import UserDB
from app.db.session import SessionLocal
from app.exceptions import UserAlreadyExistsError
from app.models.user import UserCreate
from app.services.user import UserService


@pytest.mark.integration
def test_create_and_get_user():
    session = SessionLocal()
    service = UserService(session)

    user_id = None

    try:
        user_data = UserCreate(
            name="User Service Integration Test",
            email=f"{uuid4()}@example.com",
            role="Engineer",
        )

        created_user = service.create_user(user_data)
        user_id = created_user.id

        assert created_user.name == "User Service Integration Test"
        assert created_user.email == user_data.email
        assert created_user.role == "Engineer"

        user_by_id = service.get_user_by_id(user_id)

        assert user_by_id is not None
        assert user_by_id.id == user_id

        user_by_email = service.get_user_by_email(
            user_data.email.upper()
        )

        assert user_by_email is not None
        assert user_by_email.id == user_id

    finally:
        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
            session.commit()

        session.close()
        
        
        
@pytest.mark.integration
def test_create_user_rejects_duplicate_email():
    session = SessionLocal()
    service = UserService(session)

    user_id = None

    email = f"{uuid4()}@example.com"

    try:
        first_user = service.create_user(
            UserCreate(
                name="First User",
                email=email,
                role="Engineer",
            )
        )

        user_id = first_user.id

        with pytest.raises(
            UserAlreadyExistsError,
            match="A user with this email already exists.",
        ):
            service.create_user(
                UserCreate(
                    name="Second User",
                    email=email.upper(),
                    role="Engineer",
                )
            )

    finally:
        if user_id is not None:
            session.execute(
                delete(UserDB).where(UserDB.id == user_id)
            )
            session.commit()

        session.close()