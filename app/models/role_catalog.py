from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoleResponsibilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=2000)

    @field_validator("statement")
    @classmethod
    def trim_statement(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Responsibility must not be blank.")
        return normalized


class RoleGoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Goal title must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None


class RoleCompetencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    expected_level: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Competency name must not be blank.")
        return normalized

    @field_validator("expected_level", "description")
    @classmethod
    def trim_optional_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None


class CompanyRoleWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=4000)
    responsibilities: list[RoleResponsibilityInput] = Field(
        default_factory=list, max_length=50
    )
    goals: list[RoleGoalInput] = Field(default_factory=list, max_length=50)
    competencies: list[RoleCompetencyInput] = Field(
        default_factory=list, max_length=50
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Role name must not be blank.")
        return normalized

    @field_validator("summary")
    @classmethod
    def trim_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class RoleResponsibilityResponse(BaseModel):
    id: str
    statement: str
    position: int


class RoleGoalResponse(BaseModel):
    id: str
    title: str
    description: str | None
    position: int


class RoleCompetencyResponse(BaseModel):
    id: str
    name: str
    expected_level: str | None
    description: str | None
    position: int


class CompanyRoleResponse(BaseModel):
    id: str
    name: str
    summary: str | None
    responsibilities: list[RoleResponsibilityResponse]
    goals: list[RoleGoalResponse]
    competencies: list[RoleCompetencyResponse]
    created_by_user_id: str | None
    created_at: datetime
    updated_at: datetime


class CompanyRoleHistoryResponse(BaseModel):
    id: str
    role_id: str
    role_name: str
    action: Literal["CREATED", "UPDATED", "DELETED"]
    actor_user_id: str | None
    actor_name: str
    actor_role: str
    before_snapshot: dict | None
    after_snapshot: dict | None
    created_at: datetime
