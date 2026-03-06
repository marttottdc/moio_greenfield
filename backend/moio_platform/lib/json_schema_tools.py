import json

# Map Python types → JSON-Schema types
_py2json = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _infer_schema(sample):
    if isinstance(sample, dict):
        return {
            "type": "object",
            "properties": {k: _infer_schema(v) for k, v in sample.items()},
            "required": list(sample.keys()),
            "additionalProperties": False,
        }
    if isinstance(sample, list):
        return {"type": "array", "items": _infer_schema(sample[0]) if sample else {}}
    return {"type": _py2json.get(type(sample), "string")}   # fallback to string


def merge_types(type_a, type_b):
    """
    Merge two JSON Schema types into a list of types.
    Each type can be a string or a list of strings.
    """
    if not type_a:
        return type_b
    if not type_b:
        return type_a

    if not isinstance(type_a, list):
        type_a = [type_a]
    if not isinstance(type_b, list):
        type_b = [type_b]

    return sorted(set(type_a + type_b))


def merge_properties(props_a, props_b):
    """
    Merge the 'properties' of two JSON schemas.
    """
    merged = dict(props_a)

    for key, new_prop in props_b.items():
        if key in merged:
            old_prop = merged[key]
            merged_type = merge_types(old_prop.get("type"), new_prop.get("type"))

            merged[key] = {
                **old_prop,
                **new_prop,
                "type": merged_type
            }

            # Optional: could recursively merge nested objects
            if "properties" in old_prop and "properties" in new_prop:
                merged[key]["properties"] = merge_properties(
                    old_prop["properties"],
                    new_prop["properties"]
                )

        else:
            merged[key] = new_prop

    return merged


def merge_schemas(schema_a, schema_b):
    """
    Merge two JSON Schema dicts assuming both are of type 'object'.
    """
    if not schema_a:
        return schema_b
    if not schema_b:
        return schema_a

    if schema_a.get("type") != "object" or schema_b.get("type") != "object":
        return schema_a  # fallback

    merged = {
        "type": "object",
        "properties": merge_properties(
            schema_a.get("properties", {}),
            schema_b.get("properties", {})
        ),
        "required": sorted(set(schema_a.get("required", [])) & set(schema_b.get("required", []))),
        "additionalProperties": False,
    }

    return merged



def _save_schema(cfg, schema_dict):
    cfg.expected_schema = json.dumps(schema_dict, separators=(",", ":"))
    cfg.save(update_fields=["expected_schema"])


def _load_schema(raw: str):
    """Return parsed JSON or None if empty/invalid."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None