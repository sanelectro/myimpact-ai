from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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