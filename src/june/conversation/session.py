"""Session and Turn: the immutable values of a conversation."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Self

from june.shared import DomainError

_ZERO = timedelta(0)


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{label} must not be blank")


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != _ZERO:
        raise DomainError(f"{label} must be a timezone-aware UTC datetime")


@dataclass(frozen=True, slots=True)
class Turn:
    """One user message and the agent's complete reply."""

    user_message: str
    reply: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.user_message, "user message")
        _require_text(self.reply, "reply")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Session:
    """One continuous interaction between a user and the agent."""

    id: str
    user_id: str
    created_at: datetime
    turns: tuple[Turn, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "session id")
        _require_text(self.user_id, "user id")
        _require_utc(self.created_at, "created_at")
        if not isinstance(self.turns, tuple) or not all(isinstance(t, Turn) for t in self.turns):
            raise DomainError("session turns must be a tuple of Turn")

    @classmethod
    def start(cls, user_id: str, session_id: str, now: datetime) -> Self:
        """Return a new, empty session."""
        return cls(id=session_id, user_id=user_id, created_at=now)

    def with_turn(self, turn: Turn) -> Self:
        """Return a copy of this session with `turn` appended."""
        return replace(self, turns=(*self.turns, turn))

