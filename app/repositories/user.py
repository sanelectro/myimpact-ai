from sqlalchemy.orm import Session

from app.db.models.user import UserDB
from app.utils.email import normalize_email
from app.repositories.base import BaseRepository
from datetime import UTC, datetime


class UserRepository(BaseRepository):
    def __init__(self, session: Session):
        super().__init__(session)
        
    def get_by_id(self, user_id: str) -> UserDB | None:
        return self.session.get(UserDB, user_id)
    
    def get_by_email(self, email: str) -> UserDB | None:
        normalized_email = normalize_email(email)
        return self.session.query(UserDB).filter(UserDB.email == normalized_email).first()
    
    def create(
    self,
    *,
    user_id: str,
    name: str,
    email: str,
    role: str | None = None,
) -> UserDB:
        now = datetime.now(UTC)

        user = UserDB(
            id=user_id,
            name=name,
            email=normalize_email(email),
            role=role,
            created_at=now,
            updated_at=now,
        )

        self.session.add(user)
        self.session.flush()

        return user