from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str | None = None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    role: str | None = None
