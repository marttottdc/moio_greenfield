from __future__ import annotations

from .base import (
    OperationContract,
    ResourceContract,
    output_schema_delete,
    output_schema_list,
    output_schema_object_with_id,
    schema_filter_object,
    schema_id_field,
    schema_pagination,
)


def ticket_contract() -> ResourceContract:
    slug = "ticket"
    label = "Ticket"
    description = "CRM tickets for support/work items."

    create_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "contact_id": {"type": "string"},
            "service": {"type": "string", "default": "general"},
            "description": {"type": "string"},
            "origin_session_id": {"type": "string"},
        },
        "required": ["contact_id", "description"],
    }

    update_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ticket_id": schema_id_field("ticket_id"),
            "status": {"type": "string"},
            "service": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["ticket_id"],
    }

    get_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"ticket_id": schema_id_field("ticket_id")},
        "required": ["ticket_id"],
    }

    delete_input = get_input

    list_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **schema_pagination().get("properties", {}),
            "status": {"type": "string"},
        },
    }

    filter_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "filters": schema_filter_object(
                properties={
                    "contact_id": {"type": "string"},
                    "status": {"type": "string"},
                    "service": {"type": "string"},
                }
            ),
            **schema_pagination().get("properties", {}),
        },
    }

    ops = {
        "create": OperationContract(
            op="create",
            label="Create",
            description="Create a ticket for a contact.",
            input_schema=create_input,
            output_schema=output_schema_object_with_id(object_title="Ticket"),
        ),
        "update": OperationContract(
            op="update",
            label="Update",
            description="Update a ticket by id.",
            input_schema=update_input,
            output_schema=output_schema_object_with_id(object_title="Ticket"),
        ),
        "delete": OperationContract(
            op="delete",
            label="Delete",
            description="Delete a ticket by id.",
            input_schema=delete_input,
            output_schema=output_schema_delete(),
        ),
        "get": OperationContract(
            op="get",
            label="Get details",
            description="Fetch a ticket by id.",
            input_schema=get_input,
            output_schema=output_schema_object_with_id(object_title="Ticket"),
        ),
        "list": OperationContract(
            op="list",
            label="List",
            description="List tickets (paged).",
            input_schema=list_input,
            output_schema=output_schema_list(item_title="Ticket"),
        ),
        "filter": OperationContract(
            op="filter",
            label="Filter",
            description="Filter tickets by fields (paged).",
            input_schema=filter_input,
            output_schema=output_schema_list(item_title="Ticket"),
        ),
    }

    return ResourceContract(slug=slug, label=label, description=description, operations=ops)

