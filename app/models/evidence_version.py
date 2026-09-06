from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceVersion(BaseModel):
    id: str
    evidence_id: str
    version: int = Field(ge=1)
    content: str
    content_hash: str
    source_updated_at: datetime | None = None
    captured_at: datetime
    created_at: datetime
