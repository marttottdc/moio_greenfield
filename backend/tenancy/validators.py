"""
Tenancy validators. RFC 1034/1035: hostname labels must use only a-z, 0-9, hyphen.
Underscores are not allowed in hostnames and cause Django to reject the Host header.
"""
from __future__ import annotations

import re

# RFC 1034/1035: label = 1-63 chars, a-z, 0-9, hyphen; cannot start/end with hyphen
SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def validate_subdomain_rfc(subdomain: str | None) -> None:
    """
    Validate subdomain complies with RFC 1034/1035 (valid hostname label).
    Raises ValueError with a clear message if invalid.
    """
    if not subdomain or not subdomain.strip():
        return
    s = subdomain.strip().lower()
    if not s:
        return
    if "_" in s:
        raise ValueError(
            "El subdomain no puede contener guiones bajos (_). "
            "Use solo letras minúsculas, números y guiones (ej: test2, mi-org)."
        )
    if not SUBDOMAIN_RE.match(s):
        raise ValueError(
            "El subdomain debe cumplir RFC 1034/1035: solo letras minúsculas, "
            "números y guiones; no puede comenzar ni terminar con guión (ej: test2, acme)."
        )
    if len(s) > 63:
        raise ValueError("El subdomain no puede tener más de 63 caracteres.")
