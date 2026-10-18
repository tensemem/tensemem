"""Errors raised by the registry and storage layers."""


class RegistryConflictError(ValueError):
    """A predicate, alias, or entity definition contradicts an existing one."""
