# webhooks/utils.py
import importlib
from portal.webhooks.registry import _HANDLER_REGISTRY
import secrets
from typing import Dict, Any, Callable


def available_handlers() -> dict[str, Callable]:
    """Copy so callers can’t mutate the internal dict."""
    return _HANDLER_REGISTRY.copy()


def get_handler(key: str) -> Callable:
    """Registry lookup first, dotted-path import fallback."""
    if key in _HANDLER_REGISTRY:
        return _HANDLER_REGISTRY[key]
    module, _, attr = key.rpartition(".")
    if not module:
        raise KeyError(f"Handler '{key}' not found")
    return getattr(importlib.import_module(module), attr)


def generate_auth_config(auth_type: str, **overrides) -> Dict[str, Any]:
    """
    Return a valid auth_config for WebhookConfig based on auth_type.

    Optional keyword args let you override any default value.
    Example:
        cfg = generate_auth_config("basic", username="foo", password="bar")
    """
    # sensible secure defaults
    defaults = {
        "none": {},
        "bearer": {
            "token": secrets.token_urlsafe(32),
        },
        "basic": {
            "username": overrides.get("username", "user"),
            "password": overrides.get("password", secrets.token_urlsafe(16)),
        },
        "hmac": {
            "secret": secrets.token_hex(32),
            "signature_header": overrides.get("signature_header", "X-Signature"),
        },
        "header": {
            "header": overrides.get("header", "X-Webhook-Key"),
            "value": overrides.get("value", secrets.token_urlsafe(24)),
        },
        "query": {
            "param": overrides.get("param", "token"),
            "value": overrides.get("value", secrets.token_urlsafe(24)),
        },
        "jwt": {
            # choose one of these two lines ↓ and delete the other if you
            # want to force HS256 *or* RS256; here we allow either.
            "secret": secrets.token_urlsafe(32),
            # "jwks_url": overrides.get("jwks_url"),
        },
    }

    if auth_type not in defaults:
        raise ValueError(f"Unsupported auth_type '{auth_type}'")

    # merge explicit overrides on top of defaults
    cfg = {**defaults[auth_type], **overrides}

    # lightweight sanity checks
    if auth_type == "basic" and ("username" not in cfg or "password" not in cfg):
        raise ValueError("basic auth_config needs 'username' and 'password'")
    if auth_type == "hmac" and "secret" not in cfg:
        raise ValueError("hmac auth_config needs 'secret'")
    if auth_type == "jwt" and not (cfg.get("secret") or cfg.get("jwks_url")):
        raise ValueError("jwt auth_config needs either 'secret' or 'jwks_url'")

    return cfg


def trigger_webhook_flows(webhook_name: str, payload: Dict[str, Any]) -> None:
    """Trigger any configured flows for this webhook"""
    from flows.core.connector import flow_connector
    flow_connector.trigger_webhook_flows(webhook_name, payload)

