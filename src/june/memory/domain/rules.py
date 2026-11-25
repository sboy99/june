"""Pure memory rules. Time is always passed in; nothing here does I/O."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from june.memory.domain.types import Episode, EpisodeStatus, Fact, normalize_text

DEFAULT_HALF_LIFE = timedelta(days=30)
DEFAULT_EPISODE_RETENTION = timedelta(days=180)
DEFAULT_SUPERSEDED_GRACE = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    episode_retention: timedelta = DEFAULT_EPISODE_RETENTION
    superseded_grace: timedelta = DEFAULT_SUPERSEDED_GRACE


def supersede(existing: Iterable[Fact], new: Fact) -> tuple[Fact, ...]:
    """Return the user's active facts replaced by `new`, marked superseded by it."""
    if new.profile_key is None:
        return ()
    key = normalize_text(new.profile_key)
    return tuple(
        fact.mark_superseded(new.id)
        for fact in existing
        if fact.user_id == new.user_id
        and fact.is_active
        and fact.profile_key is not None
        and normalize_text(fact.profile_key) == key
    )


def find_duplicate(existing: Iterable[Fact], candidate: Fact) -> Fact | None:
    """Return the active fact of the same user with the same normalized text."""
    text = normalize_text(candidate.text)
    for fact in existing:
        if (
            fact.user_id == candidate.user_id
            and fact.is_active
            and normalize_text(fact.text) == text
        ):
            return fact
    return None


def recency_decay(
    created_at: datetime, now: datetime, half_life: timedelta = DEFAULT_HALF_LIFE
) -> float:
    """Exponential half-life decay in (0, 1]; future-dated memories count as age zero."""
    if half_life <= timedelta(0):
        raise ValueError("half_life must be positive")
    age = max(now - created_at, timedelta(0))
    return float(0.5 ** (age / half_life))


def is_episode_expired(episode: Episode, now: datetime, policy: RetentionPolicy) -> bool:
    if episode.status is EpisodeStatus.PENDING:
        return False
    return now - episode.created_at > policy.episode_retention


def is_fact_purgeable(
    fact: Fact, superseded_at: datetime, now: datetime, policy: RetentionPolicy
) -> bool:
    """Only superseded facts are purgeable, after the grace period."""
    if fact.is_active:
        return False
    return now - superseded_at > policy.superseded_grace
