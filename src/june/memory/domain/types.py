"""Immutable memory value types: Fact, Episode, Skill."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from june.shared import DomainError


class EpisodeStatus(StrEnum):
    PENDING = "pending"
    CONSOLIDATED = "consolidated"


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{label} must not be blank")


ZERO_DURATION = timedelta(0)


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != ZERO_DURATION:
        raise DomainError(f"{label} must be a timezone-aware UTC datetime")


def normalize_text(text: str) -> str:
    """Trim, collapse inner whitespace and casefold."""
    return " ".join(text.split()).casefold()


@dataclass(frozen=True, slots=True)
class Fact:
    id: str
    user_id: str
    text: str
    source: str
    created_at: datetime
    profile_key: str | None = None
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "fact id")
        _require_text(self.user_id, "user id")
        _require_text(self.text, "fact text")
        _require_text(self.source, "fact source")
        _require_utc(self.created_at, "created_at")
        if self.profile_key is not None:
            _require_text(self.profile_key, "profile key")
        if self.superseded_by is not None:
            self._check_superseded_by(self.superseded_by)

    def _check_superseded_by(self, by_fact_id: str) -> None:
        _require_text(by_fact_id, "superseded_by")
        if by_fact_id == self.id:
            raise DomainError("a fact cannot supersede itself")

    @property
    def is_active(self) -> bool:
        return self.superseded_by is None

    def mark_superseded(self, by_fact_id: str) -> "Fact":
        self._check_superseded_by(by_fact_id)
        return replace(self, superseded_by=by_fact_id)


@dataclass(frozen=True, slots=True)
class Episode:
    id: str
    user_id: str
    summary: str
    created_at: datetime
    status: EpisodeStatus = EpisodeStatus.PENDING

    def __post_init__(self) -> None:
        _require_text(self.id, "episode id")
        _require_text(self.user_id, "user id")
        _require_text(self.summary, "episode summary")
        _require_utc(self.created_at, "created_at")
        if not isinstance(self.status, EpisodeStatus):
            raise DomainError(f"invalid episode status: {self.status!r}")

    def mark_consolidated(self) -> "Episode":
        return replace(self, status=EpisodeStatus.CONSOLIDATED)


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    description: str
    steps: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.name, "skill name")
        _require_text(self.description, "skill description")
        _require_utc(self.created_at, "created_at")
        if not isinstance(self.steps, tuple) or not self.steps:
            raise DomainError("skill steps must be a non-empty tuple")
        for step in self.steps:
            _require_text(step, "skill step")
