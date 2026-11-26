"""Use cases that turn conversations into episodes and episodes into facts."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace

from june.memory.application.remember import RememberEpisode, RememberFact
from june.memory.domain import Episode, EpisodeStatus, Fact
from june.memory.domain.helper import require_text
from june.memory.ports import IndexEntry, SearchFilter, Summarizer, TranscriptTurn, VectorIndex
from june.observability.redaction import redact_text
from june.shared import DomainError

CONSOLIDATION_SOURCE = "consolidation"
_PENDING_EPISODES = SearchFilter(kind="episode", episode_status=EpisodeStatus.PENDING)
_ACTIVE_FACTS = SearchFilter(kind="fact", active_only=True)


@dataclass(frozen=True, slots=True)
class ConsolidationResult:
    """What one consolidation run did; candidates that were secret or already known are skipped."""

    episodes_consolidated: int
    facts_stored: int
    facts_skipped: int


def contains_secret(text: str) -> bool:
    """Whether the text holds a secret-shaped substring (same patterns as log redaction)."""
    return redact_text(text) != text


class RememberConversation:
    """Summarize transcript turns and store the summary as a pending episode."""

    def __init__(self, summarizer: Summarizer, remember_episode: RememberEpisode) -> None:
        self._summarizer = summarizer
        self._remember_episode = remember_episode

    async def execute(self, user_id: str, turns: Sequence[TranscriptTurn]) -> Episode:
        require_text(user_id, "user id")
        if not turns:
            raise DomainError("a conversation needs at least one turn")
        summary = await self._summarizer.summarize(turns)
        return await self._remember_episode.execute(user_id, summary)


class Consolidate:
    """Distill a user's pending episodes into facts, then mark the episodes consolidated.

    Runs are serialized per user by an in-process lock. Episodes are marked only after
    every fact is stored, so a failure leaves them pending and a rerun dedupes.
    """

    def __init__(
        self, index: VectorIndex, summarizer: Summarizer, remember_fact: RememberFact
    ) -> None:
        self._index = index
        self._summarizer = summarizer
        self._remember_fact = remember_fact
        self._locks: dict[str, asyncio.Lock] = {}

    async def execute(self, user_id: str) -> ConsolidationResult:
        require_text(user_id, "user id")
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            return await self._consolidate(user_id)

    async def _consolidate(self, user_id: str) -> ConsolidationResult:
        pending = await self._index.list(user_id, _PENDING_EPISODES)
        if not pending:
            return ConsolidationResult(0, 0, 0)
        episodes = [entry.item for entry in pending if isinstance(entry.item, Episode)]
        candidates = await self._summarizer.distill(episodes)
        known = {entry.id for entry in await self._index.list(user_id, _ACTIVE_FACTS)}
        stored = skipped = 0
        for candidate in candidates:
            if contains_secret(candidate.text):
                skipped += 1
                continue
            fact = await self._remember_fact.execute(
                user_id, candidate.text, CONSOLIDATION_SOURCE, candidate.profile_key
            )
            if _is_new(fact, known):
                known.add(fact.id)
                stored += 1
            else:
                skipped += 1
        await self._index.upsert([_consolidated(entry) for entry in pending])
        return ConsolidationResult(len(pending), stored, skipped)


def _is_new(fact: Fact, known: set[str]) -> bool:
    return fact.id not in known


def _consolidated(entry: IndexEntry) -> IndexEntry:
    episode = entry.item
    assert isinstance(episode, Episode)
    return replace(entry, item=episode.mark_consolidated())
