# webhooks/registry.py
from typing import Callable, Dict, List, Any

_HANDLER_REGISTRY: Dict[str, Callable] = {}


def webhook_handler(name: str | None = None, description: str | None = None):
    def wrapper(fn: Callable):
        key = name or fn.__name__
        if key in _HANDLER_REGISTRY:
            raise RuntimeError(f"Duplicate webhook handler key: {key}")
        fn._webhook_handler_name = key
        fn._webhook_handler_description = description or fn.__doc__ or ""
        _HANDLER_REGISTRY[key] = fn
        return fn
    return wrapper


def get_handler(name: str) -> Callable | None:
    return _HANDLER_REGISTRY.get(name)


def get_available_handlers() -> List[Dict[str, Any]]:
    handlers = []
    for key, fn in _HANDLER_REGISTRY.items():
        doc = getattr(fn, '_webhook_handler_description', '') or fn.__doc__ or ''
        if doc:
            doc = doc.strip().split('\n')[0]
        full_path = f"{fn.__module__}.{fn.__name__}"
        handlers.append({
            "name": key,
            "path": full_path,
            "description": doc,
        })
    return sorted(handlers, key=lambda h: h["name"])






