from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


# --- Suggested activities list (for user confirmation + details) ---


class SuggestedActivityItem(BaseModel):
    """
    Single suggested activity for the user to confirm. Kinds:
    - event: interactions with contacts (calls, messages, emails, meetings including lunches)
    - task: internal work for you or team (prepare quote, prepare presentation)
    - deal: business opportunity emerging from the interaction
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["task", "event", "deal"]
    title: str
    description: Optional[str] = None
    # For task (internal work: prepare quote, presentation, etc.)
    proposed_due_at: Optional[str] = None  # ISO-8601
    priority: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    # For event (calls, messages, emails, meetings with contacts)
    proposed_start_at: Optional[str] = None
    proposed_end_at: Optional[str] = None
    location: Optional[str] = None
    attendees: list[str] = Field(default_factory=list)
    # "completed" for past events, "planned" for future (default)
    status: Optional[Literal["planned", "completed"]] = None
    # For deal (business opportunity)
    proposed_value: Optional[str] = None
    proposed_currency: Optional[str] = None
    # When true, UI should ask user for specific time/date
    needs_time_confirmation: bool = False
    # Brief reason for this suggestion
    reason: Optional[str] = None


class SuggestLinkItem(BaseModel):
    """Strict shape for OpenAI structured output (additionalProperties must be false)."""

    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    id: Optional[str] = None
    label: Optional[str] = None


class ClassificationOutput(BaseModel):
    """
    Strict contract for LLM output.

    All activities (past events, tasks, future events, deals) go in suggested_activities.
    This is the single source of truth—no duplicate fields for intents or temporal slots.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str
    channel: Literal["PHONE", "EMAIL", "WHATSAPP", "VISIT", "IN_PERSON", "WEB", "SMS", "OTHER"]
    direction: Literal["INBOUND", "OUTBOUND", "INTERNAL"]
    outcome: Literal["CONNECTED", "NO_ANSWER", "LEFT_MESSAGE", "SENT", "RECEIVED", "UNKNOWN"]

    # Single source of truth: list ALL activities here (past events, tasks, future events, deals)
    suggested_activities: list[SuggestedActivityItem] = Field(default_factory=list)

    temporal_type: Literal["past", "future", "ambiguous"] = "ambiguous"
    temporal_reasoning: Optional[str] = None
    suggest_links: list[SuggestLinkItem] = Field(default_factory=list)
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

