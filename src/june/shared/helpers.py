"""Shared validation helpers: pure functions, no I/O, no clock."""

from datetime import datetime, timedelta

from june.shared.errors import DomainError, PermanentAdapterError

ZERO_DURATION = timedelta(0)


def require_text(value: str, label: str) -> None:
    """Raise `DomainError` unless `value` is a string with non-whitespace content."""
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{label} must not be blank")


def require_utc(value: datetime, label: str) -> None:
    """Raise `DomainError` unless `value` is a timezone-aware UTC datetime."""
    if value.tzinfo is None or value.utcoffset() != ZERO_DURATION:
        raise DomainError(f"{label} must be a timezone-aware UTC datetime")


def require_adapter_text(value: str, label: str) -> None:
    """Raise `PermanentAdapterError` unless `value` has non-whitespace content."""
    if not value.strip():
        raise PermanentAdapterError(f"{label} must not be blank")
