from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Product-facing request for the MyImpact assistant."""

    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be empty")
        return value


class ChatResponse(BaseModel):
    """Product-facing response from the MyImpact assistant."""

    message: str
