"""Use case that finds the memories most relevant to a query."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from june.memory.domain import DEFAULT_HALF_LIFE, Episode, Fact, recency_decay
from june.memory.domain.helper import require_text
from june.memory.ports import Embedder, EntryKind, SearchFilter, VectorIndex
from june.shared import Clock, DomainError

DEFAULT_RECALL_LIMIT = 5
DEFAULT_CANDIDATE_MULTIPLIER = 4


@dataclass(frozen=True, slots=True)
class RecalledMemory:
    """A recalled item with its cosine `similarity`, `recency` decay and final `score`."""

    item: Fact | Episode
    similarity: float
    recency: float
    score: float


class Recall:
    """Rank memories by similarity times recency decay."""

    def __init__(
        self,
        index: VectorIndex,
        embedder: Embedder,
        clock: Clock,
        half_life: timedelta = DEFAULT_HALF_LIFE,
        candidate_multiplier: int = DEFAULT_CANDIDATE_MULTIPLIER,
    ) -> None:
        if candidate_multiplier < 1:
            raise DomainError("candidate_multiplier must be at least 1")
        self._index = index
        self._embedder = embedder
        self._clock = clock
        self._half_life = half_life
        self._candidate_multiplier = candidate_multiplier

    async def execute(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = DEFAULT_RECALL_LIMIT,
        kind: EntryKind | None = None,
        min_similarity: float = 0.0,
    ) -> list[RecalledMemory]:
        require_text(user_id, "user id")
        require_text(query, "query")
        if limit < 1:
            raise DomainError("limit must be at least 1")
        [vector] = await self._embedder.embed([query])
        hits = await self._index.search(
            user_id,
            vector,
            limit=limit * self._candidate_multiplier,
            filter=SearchFilter(kind=kind, active_only=True),
            embedder=self._embedder.info,
        )
        now = self._clock.now()
        memories = [
            self._rank(hit.entry.item, hit.score, now) for hit in hits if hit.score > min_similarity
        ]
        memories.sort(key=lambda memory: (-memory.score, memory.item.id))
        return memories[:limit]

    def _rank(self, item: Fact | Episode, similarity: float, now: datetime) -> RecalledMemory:
        recency = recency_decay(item.created_at, now, self._half_life)
        return RecalledMemory(
            item=item, similarity=similarity, recency=recency, score=similarity * recency
        )
