from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileRole(str, Enum):
    TRAINEE_ENGINEER = "Trainee Software Engineer"
    JUNIOR_ENGINEER = "Junior Software Engineer"
    SOFTWARE_ENGINEER = "Software Engineer"
    SENIOR_ENGINEER = "Senior Software Engineer"
    LEAD_ENGINEER = "Lead Software Engineer"
    LEAD_ARCHITECT = "Lead Software Architect"
    ENGINEERING_MANAGER = "Engineering Manager"
    SENIOR_ENGINEERING_MANAGER = "Senior Engineering Manager"
    ENGINEERING_DIRECTOR = "Engineering Director"


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1, max_length=200)
    team: str | None = Field(default=None, max_length=200)
    role: ProfileRole | None
    reporting_manager_id: str | None = None

    @field_validator("team")
    @classmethod
    def normalize_team(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("company")
    @classmethod
    def normalize_company(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Company name must not be blank.")
        return normalized


class DirectReportRoleUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ProfileRole


class ReportingManagerOption(BaseModel):
    id: str
    name: str
    role: str


class DirectReportOption(BaseModel):
    id: str
    name: str
    role: str | None


class TeamOption(BaseModel):
    id: str
    name: str


class ProfileResponse(BaseModel):
    user_id: str
    name: str
    email: str
    company: str | None
    organization_id: str | None
    team: str | None
    role: str | None
    reporting_manager_id: str | None
    reporting_manager: ReportingManagerOption | None
    direct_reports: list[DirectReportOption]
    direct_report_role_options: list[ProfileRole]


class ProfileUpdateResponse(ProfileResponse):
    reporting_manager_options: list[ReportingManagerOption]
