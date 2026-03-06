from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


class CreateTaskIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    do: bool
    title: Optional[str] = None
    due_at: Optional[str] = None  # ISO-8601 string (user timezone)
    owner: Optional[str] = None  # "SELF" or UUID string (kept loose for now)
    priority: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None


class AttendeeItem(BaseModel):
    """Strict shape for OpenAI structured output (additionalProperties must be false)."""

    model_config = ConfigDict(extra="forbid")

    email: Optional[str] = None
    address: Optional[str] = None


class CreateAppointmentIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    do: bool
    title: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    attendees: list[AttendeeItem] = Field(default_factory=list)
    location: Optional[str] = None
    book_calendar: bool = False


class IntentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create_task: CreateTaskIntent = Field(default_factory=lambda: CreateTaskIntent(do=False))
    create_appointment: CreateAppointmentIntent = Field(
        default_factory=lambda: CreateAppointmentIntent(do=False)
    )


class SuggestLinkItem(BaseModel):
    """Strict shape for OpenAI structured output (additionalProperties must be false)."""

    model_config = ConfigDict(extra="forbid")

    type: Optional[str] = None
    id: Optional[str] = None
    label: Optional[str] = None


class ClassificationOutput(BaseModel):
    """
    Strict contract for LLM output.

    Note: This matches the spec shape but keeps `intent` typed (not raw dict)
    so we can safely map it into ActivityRecord content.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str
    channel: Literal["PHONE", "EMAIL", "WHATSAPP", "VISIT", "IN_PERSON", "WEB", "SMS", "OTHER"]
    direction: Literal["INBOUND", "OUTBOUND", "INTERNAL"]
    outcome: Literal["CONNECTED", "NO_ANSWER", "LEFT_MESSAGE", "SENT", "RECEIVED", "UNKNOWN"]
    intent: IntentOutput
    suggest_links: list[SuggestLinkItem] = Field(default_factory=list)
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

