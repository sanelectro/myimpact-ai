from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    prompt: str = Field(min_length=1)
    response_format: dict[str, str] | None = None


class LLMResponse(BaseModel):
    content: str
    model: str | None = None