"""Hierarchy of infra-draw exceptions.

Every layer raises from a common base so callers can catch broadly or narrowly.
"""


class InfraDrawError(Exception):
    """Root exception for the whole tool."""


# --- credential / auth ---
class CredentialsError(InfraDrawError):
    """Cloud credentials are missing or invalid."""


class PermissionError_(InfraDrawError):
    """Caller lacks a required IAM / RBAC permission."""


# --- provider ---
class ProviderError(InfraDrawError):
    """A cloud provider API returned an unrecoverable error."""


class ResourceNotFoundError(InfraDrawError):
    """A specific cloud resource was not found."""


# --- diagram ---
class DiagramError(InfraDrawError):
    """Diagram generation failed."""


class GraphvizMissingError(DiagramError):
    """Graphviz ``dot`` binary is not on PATH."""


# --- config ---
class ConfigError(InfraDrawError):
    """Invalid or missing configuration."""
