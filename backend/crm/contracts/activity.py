from __future__ import annotations

from .base import (
    OperationContract,
    ResourceContract,
    output_schema_object_with_id,
)


def activity_contract() -> ResourceContract:
    slug = "activity"
    label = "Activity"
    description = "CRM activity records (planned or completed interactions)."

    create_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type_key": {"type": "string", "description": "ActivityType key (e.g. call.outbound)"},
            "title": {"type": "string"},
            "kind": {"type": "string", "default": "task"},
            "content": {"type": "object"},
            "status": {"type": "string", "enum": ["planned", "completed"], "default": "planned"},
            "scheduled_at": {"type": "string", "format": "date-time"},
            "contact_id": {"type": "string"},
            "customer_id": {"type": "string"},
            "deal_id": {"type": "string"},
            "source": {"type": "string", "enum": ["manual", "system", "suggestion"], "default": "system"},
            "reason": {"type": "string"},
        },
        "required": ["type_key"],
    }

    return ResourceContract(
        slug=slug,
        label=label,
        description=description,
        operations={
            "create": OperationContract(
                op="create",
                label="Create",
                description="Create an activity record (planned or completed).",
                input_schema=create_input,
                output_schema=output_schema_object_with_id(object_title="Activity"),
            ),
        },
    )


def activity_suggestion_contract() -> ResourceContract:
    slug = "activity_suggestion"
    label = "Activity Suggestion"
    description = "System-generated activity suggestions (accept to create an activity)."

    create_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type_key": {"type": "string"},
            "reason": {"type": "string"},
            "confidence": {"type": "number"},
            "expires_at": {"type": "string", "format": "date-time"},
            "proposed_fields": {"type": "object"},
            "target_contact_id": {"type": "string"},
            "target_customer_id": {"type": "string"},
            "target_deal_id": {"type": "string"},
            "created_by_source": {"type": "string"},
        },
        "required": ["type_key", "reason", "created_by_source"],
    }

    return ResourceContract(
        slug=slug,
        label=label,
        description=description,
        operations={
            "create": OperationContract(
                op="create",
                label="Create",
                description="Create an activity suggestion.",
                input_schema=create_input,
                output_schema=output_schema_object_with_id(object_title="ActivitySuggestion"),
            ),
        },
    )
