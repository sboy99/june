"""Shared error types used across modules."""


class JuneError(Exception):
    """Base class for expected, user-facing errors."""


class PersonaNotFoundError(JuneError):
    """Raised when the persona file is missing or empty."""
