from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.user import UserDB
from app.exceptions import UserAlreadyExistsError
from app.models.user import UserCreate
from app.repositories.user import UserRepository
from app.services.base import BaseService


class UserService(BaseService):
    def __init__(self, session: Session):
        super().__init__(session)
        self.repository = UserRepository(session)

    def create_user(self, user_data: UserCreate) -> UserDB:
        try:
            user = self.repository.create(
                user_id=str(uuid4()),
                name=user_data.name,
                email=str(user_data.email),
                role=user_data.role,
            )

            self.commit()

            return user

        except IntegrityError as exc:
            self.rollback()
            
            constraint_name = getattr(
                getattr(exc.orig, "diag", None),
                "constraint_name",
                None,
            )

            if constraint_name == "ix_users_email":
                raise UserAlreadyExistsError(
                    "A user with this email already exists."
                ) from exc

            raise

    def get_user_by_id(self, user_id: str) -> UserDB | None:
        return self.repository.get_by_id(user_id)

    def get_user_by_email(self, email: str) -> UserDB | None:
        return self.repository.get_by_email(email)