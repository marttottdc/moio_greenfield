from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_skip_tenant_bootstrap_signals: ContextVar[bool] = ContextVar("skip_tenant_bootstrap_signals", default=False)


def should_skip_tenant_bootstrap_signals() -> bool:
    return bool(_skip_tenant_bootstrap_signals.get())


@contextmanager
def skip_tenant_bootstrap_signals() -> Iterator[None]:
    token = _skip_tenant_bootstrap_signals.set(True)
    try:
        yield
    finally:
        _skip_tenant_bootstrap_signals.reset(token)
