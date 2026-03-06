
import os
import base64
import inspect

from django.utils import timezone
from datetime import timedelta
from typing import Dict, Any, List


def get_config_value(key, default=None):
    secret_path = "/run/secrets/app_config"
    if os.path.exists(secret_path):
        print("Secretos Encontrados !")
        with open(secret_path, 'r') as secret_file:
            secret_content = secret_file.read()
            # print("secret_content: ", secret_content)
            # decoded_data = base64.b64decode(secret_content).decode('utf-8')

            for line in secret_content.splitlines():
                if line.strip().startswith(f"{key}="):
                    value = line.strip().split("=", 1)[1]
                    print(f"Valor: {value}")
                    return str(value)
    return os.getenv(key, default)


def function_to_spec(func) -> dict:
    """
    Returns an OpenAI function call-style schema merged with JSON Schema typing
    and docstring-based parameter descriptions.
    """
    # Type mapping for JSON Schema
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    # Get docstring, default to empty if None
    doc = func.__doc__ or ""

    # Get function signature
    signature = inspect.signature(func)
    parameter_names = [param.name for param in signature.parameters.values() if param.name != "self"]

    # Split docstring into lines
    doc_lines = [line for line in doc.split("\n")]

    # Find the index of the first line that starts with ":"
    first_field_index = next((i for i, line in enumerate(doc_lines) if line.strip().startswith(":")), len(doc_lines))

    # Function description is all lines before the first field, stripped of whitespace
    function_description = "\n".join(doc_lines[:first_field_index]).strip()

    # Parse parameter descriptions after the function description
    param_descriptions = {param: "" for param in parameter_names}
    current_param = None
    for line in doc_lines[first_field_index:]:
        stripped_line = line.strip()
        if stripped_line.startswith(":param "):
            for param in parameter_names:
                if stripped_line.startswith(f":param {param}:"):
                    current_param = param
                    parts = stripped_line.split(":", 2)
                    desc = parts[2].strip() if len(parts) > 2 else ""
                    param_descriptions[param] = desc
                    break
            else:
                current_param = None
        elif line.startswith(" ") and current_param:
            # Append indented continuation lines to the current parameter's description
            param_descriptions[current_param] += " " + line.strip()
        else:
            current_param = None

    # Build schema properties
    properties = {}
    required_params = []
    for param in signature.parameters.values():
        if param.name == "self":
            continue
        json_type = type_map.get(param.annotation, "string")
        if param.default == inspect.Parameter.empty:
            required_params.append(param.name)
        properties[param.name] = {
            "type": json_type,
            "description": param_descriptions.get(param.name, ""),
        }

    # Construct the schema
    schema = {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": function_description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_params,
            },
        },
    }
    return schema


def has_time_passed(last_time, minutes=5):
    """
    Check if more than 'minutes' have passed since the given datetime field in an instance.

    :param last_time: datetime value to compare vs current
    :param minutes: Number of minutes to compare
    :return: True if more than 'minutes' have passed, False otherwise
    """

    if last_time is None:
        raise ValueError("last_time cannot be None")

    threshold_time = timezone.now() - timedelta(minutes=minutes)
    return last_time < threshold_time


def validate_object(obj: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """
    Validate an object against a schema and return a list of validation issues.
    Returns empty list if object is valid.
    """
    # Check if inputs are dictionaries
    if not isinstance(obj, dict) or not isinstance(schema, dict):
        return ["Invalid input: object and schema must be dictionaries"]

    issues = []

    # Check each property in schema
    for key, schema_def in schema.items():
        # Check if value exists in object
        value = obj.get(key)

        # Check required fields
        if schema_def.get('required', False) and key not in obj:
            issues.append(f"Property '{key}' is required but missing")
            continue

        # Skip further checks if property is missing and not required
        if key not in obj:
            continue

        # Check type
        if 'type' in schema_def:
            expected_type = schema_def['type'].lower()
            actual_type = type(value).__name__

            # Handle array/list case
            if expected_type == 'array':
                expected_type = 'list'

            if actual_type != expected_type:
                issues.append(
                    f"Property '{key}' should be type '{expected_type}', but got '{actual_type}'"
                )
                continue

        # Check nested objects
        if schema_def.get('type') == 'object' and 'properties' in schema_def:
            if isinstance(value, dict):
                nested_issues = validate_object(value, schema_def['properties'])
                issues.extend([f"{key}.{issue}" for issue in nested_issues])
            else:
                # Type check already caught this, so we continue
                continue

        # Check array items
        if schema_def.get('type') == 'array' and 'items' in schema_def:
            if isinstance(value, list):
                item_type = schema_def['items'].get('type', '').lower()
                for i, item in enumerate(value):
                    actual_type = type(item).__name__
                    if actual_type != item_type:
                        issues.append(
                            f"Item at {key}[{i}] should be type '{item_type}', but got '{actual_type}'"
                        )
            # Type check already caught non-list cases

    return issues


def check_elapsed_time(start_time, checkpoint_name):

    stage1_time = timezone.now()  # Capture end time
    stage1_elapsed_time = stage1_time - start_time  # Calculate elapsed time
    message = f"Elapsed time from {checkpoint_name}: {stage1_elapsed_time.total_seconds()} seconds"
    return message


def remove_keys(obj, keys_to_remove):
    """Return a copy of obj (dict or list) with given keys removed at all levels."""
    if isinstance(obj, dict):
        return {
            k: remove_keys(v, keys_to_remove)
            for k, v in obj.items()
            if k not in keys_to_remove
        }
    elif isinstance(obj, list):
        return [remove_keys(i, keys_to_remove) for i in obj]
    else:
        return obj
