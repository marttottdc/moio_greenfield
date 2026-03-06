# rules_prompt.py
from __future__ import annotations
from typing import Dict, Tuple
import json


def build_rules_instructions(
    field_synonyms: Dict[str, str],
    op_synonyms: Dict[str, str],
    field_allowlist: Tuple[str, ...],
    *,
    default_case_ci: bool = True,
) -> str:
    """
    Returns a compact, deterministic instruction string for the LLM.
    The model must output ONLY JSON matching your Pydantic schema.
    """
    default_case_line = (
        "- Default matching is CASE-INSENSITIVE for string fields. Do not include \"case\" unless case-sensitive is truly required."
        if default_case_ci else
        "- Default matching is CASE-SENSITIVE. Include \"case\":\"ci\" if you want case-insensitive."
    )

    # Keep JSON single-line to avoid the model hallucinating formatting.
    fld_syn = json.dumps(field_synonyms, ensure_ascii=False, separators=(",", ":"))
    op_syn  = json.dumps(op_synonyms, ensure_ascii=False, separators=(",", ":"))
    allow   = json.dumps(sorted(field_allowlist), ensure_ascii=False, separators=(",", ":"))

    return f"""
You are a compiler from natural language audience descriptions to strict JSON rules.

OUTPUT FORMAT:
- Output ONLY a JSON object that matches the provided JSON Schema (no prose, no comments).
- Key: "rules" → array of rule objects.

MAPPING REQUIREMENTS:
- Map natural field names to CANONICAL field keys using this table (synonyms → canonical):
  {fld_syn}
- Use ONLY these allowed canonical fields (dunder paths allowed):
  {allow}
- Map natural operators/phrases to CANONICAL ops using this table (synonyms → canonical):
  {op_syn}
- Emit ONLY canonical ops that the schema allows.

CASE POLICY:
{default_case_line}

LOGIC POLICY:
- Rules without an 'or_group' are ANDed together.
- To OR multiple rules, emit the same non-empty string in 'or_group' (e.g., "emails").

CONSTRAINTS:
- Dates must be ISO-8601 strings when used.
- 'between' requires both 'value' and 'value_to'.
- 'in' uses an array for 'value'.
- Do not invent fields or operators. If uncertain, pick the closest valid mapping.

EXAMPLES:
User: contactos cuyo teléfono comienza en +598
→ {{"rules":[{{"field":"phone","op":"startswith","value":"+598"}}]}}

User: company is ACME and email ends with .org
→ {{"rules":[{{"field":"company__name","op":"eq","value":"ACME"}},{{"field":"email","op":"endswith","value":".org"}}]}}

User: name equals Martin or John
→ {{"rules":[{{"field":"name","op":"eq","value":"Martin","or_group":"names"}},{{"field":"name","op":"eq","value":"John","or_group":"names"}}]}}
""".strip()
