from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    prompt: str = Field(min_length=1)


class LLMResponse(BaseModel):
    content: str
    model: str | None = None