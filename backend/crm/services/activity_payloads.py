# activity_payloads.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class TaskPayload(BaseModel):
    description: str
    due_date: datetime
    priority: int = Field(ge=1, le=5)
    status: str = Field(default="open", pattern="^(open|in_progress|done)$")


class NotePayload(BaseModel):
    body: str
    tags: List[str] = []


class IdeaPayload(BaseModel):
    body: str
    impact: int = Field(ge=1, le=10)
    tags: List[str] = []


class EventPayload(BaseModel):
    start: datetime
    end: datetime
    location: Optional[str] = None
    participants: List[str] = []


# Map for quick look-up
PAYLOAD_MODEL_BY_KIND = {
    "task": TaskPayload,
    "note": NotePayload,
    "idea": IdeaPayload,
    "event": EventPayload,
}

