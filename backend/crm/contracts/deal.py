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


def deal_contract() -> ResourceContract:
    slug = "deal"
    label = "Deal"
    description = "CRM deals/opportunities."

    create_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "value": {"type": "number"},
            "currency": {"type": "string", "default": "USD"},
            "status": {"type": "string"},
            "priority": {"type": "string"},
            "contact_id": {"type": "string"},
            "pipeline_id": {"type": "string"},
            "stage_id": {"type": "string"},
        },
        "required": ["title"],
    }

    update_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "deal_id": schema_id_field("deal_id"),
            "title": {"type": "string"},
            "description": {"type": "string"},
            "value": {"type": "number"},
            "currency": {"type": "string"},
            "status": {"type": "string"},
            "priority": {"type": "string"},
            "contact_id": {"type": "string"},
            "pipeline_id": {"type": "string"},
            "stage_id": {"type": "string"},
        },
        "required": ["deal_id"],
    }

    get_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"deal_id": schema_id_field("deal_id")},
        "required": ["deal_id"],
    }

    delete_input = get_input

    list_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {**schema_pagination().get("properties", {}), "status": {"type": "string"}},
    }

    filter_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "filters": schema_filter_object(
                properties={
                    "status": {"type": "string"},
                    "priority": {"type": "string"},
                    "contact_id": {"type": "string"},
                    "pipeline_id": {"type": "string"},
                    "stage_id": {"type": "string"},
                }
            ),
            **schema_pagination().get("properties", {}),
        },
    }

    ops = {
        "create": OperationContract(
            op="create",
            label="Create",
            description="Create a deal.",
            input_schema=create_input,
            output_schema=output_schema_object_with_id(object_title="Deal"),
        ),
        "update": OperationContract(
            op="update",
            label="Update",
            description="Update a deal by id.",
            input_schema=update_input,
            output_schema=output_schema_object_with_id(object_title="Deal"),
        ),
        "delete": OperationContract(
            op="delete",
            label="Delete",
            description="Delete a deal by id.",
            input_schema=delete_input,
            output_schema=output_schema_delete(),
        ),
        "get": OperationContract(
            op="get",
            label="Get details",
            description="Fetch a deal by id.",
            input_schema=get_input,
            output_schema=output_schema_object_with_id(object_title="Deal"),
        ),
        "list": OperationContract(
            op="list",
            label="List",
            description="List deals (paged).",
            input_schema=list_input,
            output_schema=output_schema_list(item_title="Deal"),
        ),
        "filter": OperationContract(
            op="filter",
            label="Filter",
            description="Filter deals by fields (paged).",
            input_schema=filter_input,
            output_schema=output_schema_list(item_title="Deal"),
        ),
    }

    return ResourceContract(slug=slug, label=label, description=description, operations=ops)

