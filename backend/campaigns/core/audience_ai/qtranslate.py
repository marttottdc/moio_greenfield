"""
Translate a :class:`RuleTree` into a Django :class:`~django.db.models.Q`
object. This allows the tree to be executed as a database filter on
Django ORM querysets. Each leaf rule becomes a Q object on the
corresponding field and operation; internal nodes combine child Qs
according to their logic (AND or OR).

This module does not enforce allowed field lists; callers should
pre-filter or validate field names before translation. Case sensitivity
defaults to case-insensitive when not specified in the rule. Override
``default_ci`` to change this behaviour.

Example::

    from audience_ai_min.rules import RuleNode, Rule
    from audience_ai_min.qtranslate import tree_to_q
    from crm.models import Contact

    tree = RuleNode(logic="and", children=[
        Rule(field="email", op="endswith", value="example.com"),
        RuleNode(logic="or", children=[
            Rule(field="city", op="eq", value="Montevideo"),
            Rule(field="city", op="eq", value="Buenos Aires"),
        ])
    ])
    q = tree_to_q(Contact, tree)
    contacts = Contact.objects.filter(q)

"""

from __future__ import annotations

from typing import Optional, Sequence

from django.db.models import Q, Model

from .rules import RuleNode, Rule


def _rule_to_q(rule: Rule, *, default_ci: bool = True) -> Q:
    """Convert a single :class:`Rule` into a Django Q object.

    Args:
        rule: The rule to translate.
        default_ci: Whether to use case-insensitive lookups when the
            rule does not specify a ``case``. Defaults to True.

    Returns:
        A Q object representing the rule. For negative comparisons
        (``op == 'neq'``) the Q is negated accordingly.
    """
    # Determine case preference: explicit wins, else default
    case_flag = rule.case or ("ci" if default_ci else "cs")
    ci = case_flag == "ci"

    field = rule.field
    op = rule.op
    value = rule.value
    value_to = rule.value_to

    # Map operations to Django lookups. Some ops require negation.
    if op == "eq":
        lookup = f"{field}__iexact" if ci else f"{field}__exact"
        return Q(**{lookup: value})
    elif op == "neq":
        lookup = f"{field}__iexact" if ci else f"{field}__exact"
        return ~Q(**{lookup: value})
    elif op == "contains":
        lookup = f"{field}__icontains" if ci else f"{field}__contains"
        return Q(**{lookup: value})
    elif op == "startswith":
        lookup = f"{field}__istartswith" if ci else f"{field}__startswith"
        return Q(**{lookup: value})
    elif op == "endswith":
        lookup = f"{field}__iendswith" if ci else f"{field}__endswith"
        return Q(**{lookup: value})
    elif op == "regex":
        lookup = f"{field}__iregex" if ci else f"{field}__regex"
        return Q(**{lookup: value})
    elif op == "in":
        return Q(**{f"{field}__in": value})
    elif op == "between":
        return Q(**{f"{field}__range": (value, value_to)})
    elif op in {"gt", "gte", "lt", "lte"}:
        return Q(**{f"{field}__{op}": value})
    elif op == "isnull":
        return Q(**{f"{field}__isnull": bool(value)})
    elif op == "istrue":
        return Q(**{field: True})
    elif op == "isfalse":
        return Q(**{field: False})
    else:
        # Unknown operation should not occur due to validation, but fallback
        return Q()


def _node_to_q(node: RuleNode, *, default_ci: bool = True) -> Q:
    """Recursively convert a :class:`RuleNode` into a Q object."""
    # Combine children according to logic
    if node.logic == "and":
        result = Q()
        for child in node.children:
            if isinstance(child, RuleNode):
                result &= _node_to_q(child, default_ci=default_ci)
            else:
                result &= _rule_to_q(child, default_ci=default_ci)
        return result
    else:  # "or"
        result = Q()
        for child in node.children:
            if isinstance(child, RuleNode):
                result |= _node_to_q(child, default_ci=default_ci)
            else:
                result |= _rule_to_q(child, default_ci=default_ci)
        return result


def tree_to_q(
    model: type[Model],
    tree: RuleNode,
    *,
    allowed_fields: Optional[Sequence[str]] = None,
    default_ci: bool = True,
) -> Q:
    """Entry point to convert a rule tree into a Django Q.

    Args:
        model: The Django model class the rules apply to. Currently unused
            but reserved for potential field type introspection.
        tree: The top-level rule tree returned from the LLM.
        allowed_fields: Optional iterable of canonical field names. If
            provided, any rule referencing a field not in this list will
            be ignored when building the Q.
        default_ci: Whether to default unspecified case to case-insensitive.

    Returns:
        A Q object representing the entire tree. If no valid rules are
        present (e.g. all fields are filtered out), an empty Q object
        (matching all rows) will be returned.
    """
    # Filter out invalid rules based on allowed_fields if provided
    def prune(node: RuleNode) -> Optional[RuleNode]:
        new_children = []
        for child in node.children:
            if isinstance(child, RuleNode):
                sub = prune(child)
                if sub is not None:
                    new_children.append(sub)
            else:
                if allowed_fields is None or child.field in allowed_fields:
                    new_children.append(child)
        if not new_children:
            return None
        return RuleNode(logic=node.logic, children=new_children)

    pruned = prune(tree)
    if pruned is None:
        return Q()
    return _node_to_q(pruned, default_ci=default_ci)
