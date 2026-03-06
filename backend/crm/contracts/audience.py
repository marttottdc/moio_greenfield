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


def audience_contract() -> ResourceContract:
    slug = "audience"
    label = "Audience"
    description = "Campaign audiences (static or dynamic recipient lists)."

    create_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "kind": {"type": "string", "enum": ["static", "dynamic"], "default": "static"},
            "rules": {"type": ["object", "array", "null"]},
            "is_draft": {"type": "boolean", "default": True},
        },
        "required": ["name"],
    }

    update_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "audience_id": schema_id_field("audience_id"),
            "name": {"type": "string"},
            "description": {"type": "string"},
            "kind": {"type": "string", "enum": ["static", "dynamic"]},
            "rules": {"type": ["object", "array", "null"]},
            "is_draft": {"type": "boolean"},
        },
        "required": ["audience_id"],
    }

    get_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"audience_id": schema_id_field("audience_id")},
        "required": ["audience_id"],
    }

    delete_input = get_input

    list_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {**schema_pagination().get("properties", {}), "kind": {"type": "string"}},
    }

    filter_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "filters": schema_filter_object(
                properties={
                    "kind": {"type": "string"},
                    "name_contains": {"type": "string"},
                    "is_draft": {"type": "boolean"},
                }
            ),
            **schema_pagination().get("properties", {}),
        },
    }

    ops = {
        "create": OperationContract(
            op="create",
            label="Create",
            description="Create an audience.",
            input_schema=create_input,
            output_schema=output_schema_object_with_id(object_title="Audience"),
        ),
        "update": OperationContract(
            op="update",
            label="Update",
            description="Update an audience by id.",
            input_schema=update_input,
            output_schema=output_schema_object_with_id(object_title="Audience"),
        ),
        "delete": OperationContract(
            op="delete",
            label="Delete",
            description="Delete an audience by id.",
            input_schema=delete_input,
            output_schema=output_schema_delete(),
        ),
        "get": OperationContract(
            op="get",
            label="Get details",
            description="Fetch an audience by id.",
            input_schema=get_input,
            output_schema=output_schema_object_with_id(object_title="Audience"),
        ),
        "list": OperationContract(
            op="list",
            label="List",
            description="List audiences (paged).",
            input_schema=list_input,
            output_schema=output_schema_list(item_title="Audience"),
        ),
        "filter": OperationContract(
            op="filter",
            label="Filter",
            description="Filter audiences by fields (paged).",
            input_schema=filter_input,
            output_schema=output_schema_list(item_title="Audience"),
        ),
    }

    return ResourceContract(slug=slug, label=label, description=description, operations=ops)

