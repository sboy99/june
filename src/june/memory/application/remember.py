"""Use cases that store facts and episodes."""

from dataclasses import replace

from june.memory.domain import Episode, Fact, find_duplicate, supersede
from june.memory.ports import Embedder, IndexEntry, SearchFilter, VectorIndex
from june.shared import Clock, IdGenerator

_ACTIVE_FACTS = SearchFilter(kind="fact", active_only=True)


class RememberFact:
    """Store a fact, skipping duplicates and superseding facts with the same profile key."""

    def __init__(
        self, index: VectorIndex, embedder: Embedder, clock: Clock, ids: IdGenerator
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._clock = clock
        self._ids = ids

    async def execute(
        self, user_id: str, text: str, source: str, profile_key: str | None = None
    ) -> Fact:
        fact = Fact(
            id=self._ids.new_id(),
            user_id=user_id,
            text=text,
            source=source,
            created_at=self._clock.now(),
            profile_key=profile_key,
        )
        existing_entries = await self._index.list(user_id, _ACTIVE_FACTS)
        existing = [entry.item for entry in existing_entries if isinstance(entry.item, Fact)]
        duplicate = find_duplicate(existing, fact)
        if duplicate is not None:
            return duplicate
        [vector] = await self._embedder.embed([fact.text])
        superseded = {old.id: old for old in supersede(existing, fact)}
        updated = [
            replace(entry, item=superseded[entry.id])
            for entry in existing_entries
            if entry.id in superseded
        ]
        new_entry = IndexEntry(item=fact, vector=vector, embedder=self._embedder.info)
        await self._index.upsert([new_entry, *updated])
        return fact


class RememberEpisode:
    """Store an episode summary as a pending episode."""

    def __init__(
        self, index: VectorIndex, embedder: Embedder, clock: Clock, ids: IdGenerator
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._clock = clock
        self._ids = ids

    async def execute(self, user_id: str, summary: str) -> Episode:
        episode = Episode(
            id=self._ids.new_id(),
            user_id=user_id,
            summary=summary,
            created_at=self._clock.now(),
        )
        [vector] = await self._embedder.embed([episode.summary])
        await self._index.upsert(
            [IndexEntry(item=episode, vector=vector, embedder=self._embedder.info)]
        )
        return episode
