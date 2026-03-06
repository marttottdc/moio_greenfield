
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime

# Pydantic Models
class BaseActivityData(BaseModel):
    description: Optional[str] = None
    created_by: str = Field(..., description="User who created the activity")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }

class EmailActivity(BaseActivityData):
    subject: str
    recipients: List[EmailStr]
    body: str
    sent_at: Optional[datetime] = None
    status: str = Field(default="draft", description="e.g., draft, sent, failed")

class ConversationActivity(BaseActivityData):
    participants: List[str]
    transcript: Optional[str] = None
    channel: str = Field(..., description="e.g., phone, chat, in-person")
    duration_minutes: Optional[int] = None

class TaskActivity(BaseActivityData):
    due_date: Optional[datetime] = None
    priority: str = Field(default="medium", description="e.g., low, medium, high")
    status: str = Field(default="pending", description="e.g., pending, completed")
    assignee: Optional[str] = None

class OpportunityActivity(BaseActivityData):
    deal_size: Optional[float] = None
    stage: str = Field(default="prospect", description="e.g., prospect, negotiation, closed")
    probability: Optional[float] = Field(None, ge=0, le=100, description="Probability of closing (%)")
    account: Optional[str] = None

class MeetingActivity(BaseActivityData):
    location: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    attendees: List[str] = Field(default_factory=list)

class NoteActivity(BaseActivityData):
    content: str
    related_to: Optional[str] = None  # e.g., related to another activity or entity