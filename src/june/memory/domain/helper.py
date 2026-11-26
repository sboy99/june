"""Shared helpers for the memory domain.

Anything inside `june.memory.domain` that more than one file needs lives
here (see ADR 0008). Pure functions only: no I/O, no clock.
"""

from june.shared import DomainError


def require_text(value: str, label: str) -> None:
    """Raise `DomainError` unless `value` is a string with non-whitespace content."""
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{label} must not be blank")
