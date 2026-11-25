"""Clock abstraction returning timezone-aware UTC datetimes."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Source of the current time."""

    def now(self) -> datetime: ...


class SystemClock:
    """Real clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Test clock that returns a set time until advanced."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._current = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> None:
        self._current = self._current + delta
