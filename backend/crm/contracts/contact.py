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


def contact_contract() -> ResourceContract:
    slug = "contact"
    label = "Contact"
    description = "CRM contacts (people/companies) used across tickets, deals, and messaging."

    create_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "fullname": {"type": "string"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
            "whatsapp_name": {"type": "string"},
            "source": {"type": "string", "default": "flow"},
            "contact_type_id": {"type": "string"},
            "contact_type_name": {"type": "string"},
        },
        "required": ["fullname", "phone"],
    }

    update_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "contact_id": schema_id_field("contact_id"),
            "fullname": {"type": "string"},
            "phone": {"type": "string"},
            "email": {"type": "string"},
            "whatsapp_name": {"type": "string"},
            "source": {"type": "string"},
            "contact_type_id": {"type": "string"},
            "contact_type_name": {"type": "string"},
        },
        "required": ["contact_id"],
    }

    get_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"contact_id": schema_id_field("contact_id")},
        "required": ["contact_id"],
    }

    delete_input = get_input

    list_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {**schema_pagination().get("properties", {}), "q": {"type": "string"}},
    }

    filter_input = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "filters": schema_filter_object(
                properties={
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                    "fullname_contains": {"type": "string"},
                }
            ),
            **schema_pagination().get("properties", {}),
        },
    }

    ops = {
        "create": OperationContract(
            op="create",
            label="Create",
            description="Create (or upsert) a contact.",
            input_schema=create_input,
            output_schema=output_schema_object_with_id(object_title="Contact"),
        ),
        "update": OperationContract(
            op="update",
            label="Update",
            description="Update a contact by id.",
            input_schema=update_input,
            output_schema=output_schema_object_with_id(object_title="Contact"),
        ),
        "delete": OperationContract(
            op="delete",
            label="Delete",
            description="Delete a contact by id.",
            input_schema=delete_input,
            output_schema=output_schema_delete(),
        ),
        "get": OperationContract(
            op="get",
            label="Get details",
            description="Fetch a contact by id.",
            input_schema=get_input,
            output_schema=output_schema_object_with_id(object_title="Contact"),
        ),
        "list": OperationContract(
            op="list",
            label="List",
            description="List contacts (paged).",
            input_schema=list_input,
            output_schema=output_schema_list(item_title="Contact"),
        ),
        "filter": OperationContract(
            op="filter",
            label="Filter",
            description="Filter contacts by fields (paged).",
            input_schema=filter_input,
            output_schema=output_schema_list(item_title="Contact"),
        ),
    }

    return ResourceContract(slug=slug, label=label, description=description, operations=ops)

