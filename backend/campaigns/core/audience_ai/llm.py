"""
Interaction with the OpenAI Responses API to generate rule trees from
natural-language descriptions. This module provides a single entry point
``generate_rules_tree`` that accepts a prompt, connects to the model using
the supplied OpenAI client, and returns a parsed :class:`RuleTree`.

The assistant instructs the language model via a deterministic system
prompt. It informs the model of the allowed fields and operations,
describes the expected JSON output shape (a nested tree of rules),
and optionally provides synonym mappings for fields and operations.

The client must be an instance of :class:`openai.OpenAI`. The caller
should configure the correct API key on the client before calling this
function.
"""

from __future__ import annotations
from typing import Mapping, Sequence, Optional, Any, Dict
from openai import OpenAI, Client
from central_hub.models import TenantConfiguration





def generate_rules_tree(
    config: TenantConfiguration,
    prompt: str,
    *,
    allowed_fields: Sequence[str],
    allowed_ops: Sequence[str],
    field_synonyms: Optional[Mapping[str, str]] = None,
    op_synonyms: Optional[Mapping[str, str]] = None,
    default_case_ci: bool = True,
) -> RuleTree:
    """Generate a :class:`RuleTree` from a natural-language audience description.

    Args:
        client: Configured OpenAI client. Must have API key set.
        prompt: Natural-language description of the desired audience filter.
        allowed_fields: Iterable of canonical field names that the model
            may reference in rules.
        allowed_ops: Iterable of canonical operation names permitted in
            rules. Should correspond to :data:`ALLOWED_OPS`.
        field_synonyms: Optional mapping of lowercase synonyms to canonical
            field names. If provided, the model may use these synonyms
            which will then be resolved to the canonical names.
        op_synonyms: Optional mapping of lowercase synonyms to canonical
            operation names. Similar to ``field_synonyms`` but for ops.
        default_case_ci: Whether to default unspecified case to
            case-insensitive (True for "ci", False for "cs").
        openai_model: Name of the Responses API model. Defaults to
            ``"gpt-4.1-mini"`` which currently supports response schemas.

    Returns:
        A :class:`RuleTree` parsed from the model's JSON output. The tree
        will have canonical field and operation names and explicit case
        flags filled in.

    Raises:
        pydantic.ValidationError: If the returned JSON cannot be parsed
            into the rule schema.
    """
    # Build the system prompt with allowed field/op lists and synonyms
    synonyms_lines: list[str] = []

    if field_synonyms:
        synonyms_lines.append("Field synonyms:")
        for k, v in field_synonyms.items():
            synonyms_lines.append(f"- '{k}' => '{v}'")

    if op_synonyms:
        synonyms_lines.append("Operation synonyms:")
        for k, v in op_synonyms.items():
            synonyms_lines.append(f"- '{k}' => '{v}'")

    default_case = "ci" if default_case_ci else "cs"

    sys_prompt = (
        "You are a helpful assistant that converts natural-language descriptions "
        "of contact audiences into structured JSON rule trees. Use only the "
        "allowed fields and operations listed below. Rules are expressed in a "
        "JSON object with keys 'logic' and 'children'. 'logic' may be either "
        "'and' or 'or' and 'children' is an array of either nested objects or "
        "rule leaves. A rule leaf has the fields: 'field', 'op', 'value', "
        "'value_to', and 'case'. The 'case' field controls case-sensitivity "
        "for text-based ops and may be 'ci' for case-insensitive or 'cs' for "
        "case-sensitive. If omitted, default to '"
        + default_case
        + "'. For 'between' operations, include both 'value' and 'value_to'. For "
        "'in', provide an array in 'value'. For 'isnull', set 'value' to true "
        "for null and false for not null. Do not include extraneous keys. "
        "Allowed fields: "
        + ", ".join(allowed_fields)
        + ". Allowed ops: "
        + ", ".join(allowed_ops)
        + "."
    )

    if synonyms_lines:
        sys_prompt += " Use the following synonyms when appropriate: " + "\n".join(synonyms_lines)

    # Use the Responses API with json_object format for strict JSON
    from audience_rules import AudienceRules

    client = OpenAI(api_key=config.openai_api_key)
    resp = client.responses.parse(
        model=config.openai_default_model,
        instructions=sys_prompt,
        input=prompt,
        text_format=AudienceRules
    )

    json_data: Any = resp.output_parsed

    print(json_data)

    # Apply synonyms and default case to the raw JSON
   #syn_data = _apply_synonyms_json(
   #     json_data,
   #     field_synonyms=field_synonyms,
   #     op_synonyms=op_synonyms,
   #     default_case=default_case,
   # )

    return json_data  # type: ignore[return-value]
