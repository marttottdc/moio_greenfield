"""Integration Hub exceptions."""


class IntegrationHubError(Exception):
    """Base for integration hub errors."""


class ProviderError(IntegrationHubError):
    """Provider request or config error."""


class ValidationError(IntegrationHubError):
    """Invalid request payload or schema."""


class AuthError(IntegrationHubError):
    """Auth or credential resolution failed."""


class PathNotAllowedError(IntegrationHubError):
    """Path/method not allowed by policy (used when policy is closed)."""
