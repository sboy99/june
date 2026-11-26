"""Ports (interfaces) of the memory module.

Port-level value types are immutable. Every port method is async. Only
`TransientAdapterError` (retryable) and `PermanentAdapterError` (not
retryable) may escape an adapter; vendor exceptions never do, and error text
never contains secrets or API keys.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from june.memory.domain import Episode, EpisodeStatus, Fact, Skill
from june.shared import DomainError

Vector = tuple[float, ...]


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{label} must not be blank")


@dataclass(frozen=True, slots=True)
class EmbedderInfo:
    """Identity of an embedder: stored with every vector so a model change is detectable."""

    name: str
    version: str
    dimensions: int

    def __post_init__(self) -> None:
        _require_text(self.name, "embedder name")
        _require_text(self.version, "embedder version")
        if self.dimensions < 1:
            raise DomainError("embedder dimensions must be positive")


class Embedder(Protocol):
    """Port: turns texts into vectors.

    Contract every adapter must meet:

    - Return exactly one vector per input text, in input order, each with
      `info.dimensions` finite floats.
    - The same text gives the same vector for the same `info.name` and
      `info.version`.
    - An empty batch returns an empty list without calling the vendor.
    - Blank text is allowed (callers filter).
    - Retry transient failures internally, up to the configured retry count,
      then raise `TransientAdapterError`; permanent failures raise
      `PermanentAdapterError`.
    """

    @property
    def info(self) -> EmbedderInfo: ...

    async def embed(self, texts: Sequence[str]) -> list[Vector]: ...


EntryKind = Literal["fact", "episode"]
_ENTRY_KINDS = ("fact", "episode")


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """A Fact or Episode stored with its vector and the identity of the embedder that made it.

    The index is the only store of Facts and Episodes, so `item` is the full
    domain object, including `superseded_by` and episode status.
    """

    item: Fact | Episode
    vector: Vector
    embedder: EmbedderInfo

    def __post_init__(self) -> None:
        if len(self.vector) != self.embedder.dimensions:
            raise DomainError("vector length must equal embedder dimensions")
        if not all(math.isfinite(x) for x in self.vector):
            raise DomainError("vector values must be finite")

    @property
    def id(self) -> str:
        return self.item.id

    @property
    def user_id(self) -> str:
        return self.item.user_id

    @property
    def kind(self) -> EntryKind:
        return "fact" if isinstance(self.item, Fact) else "episode"


@dataclass(frozen=True, slots=True)
class SearchFilter:
    """Narrow a search or listing. Defaults match everything.

    `active_only` excludes superseded facts (episodes are unaffected);
    `episode_status` excludes episodes with another status (facts are unaffected
    unless `kind` is also set).
    """

    kind: EntryKind | None = None
    active_only: bool = False
    episode_status: EpisodeStatus | None = None

    def __post_init__(self) -> None:
        if self.kind is not None and self.kind not in _ENTRY_KINDS:
            raise DomainError(f"invalid entry kind: {self.kind!r}")


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One search result; `score` is cosine similarity in [-1, 1], higher is closer."""

    entry: IndexEntry
    score: float

    def __post_init__(self) -> None:
        if not -1.0 <= self.score <= 1.0:
            raise DomainError("score must be within [-1, 1]")


class VectorIndex(Protocol):
    """Port: stores entries and finds the nearest ones for one user.

    Contract every adapter must meet:

    - A `filter` of None matches everything.
    - Every method is scoped to `user_id`; one user's entries are never
      returned, changed or deleted by another user's call.
    - `upsert` replaces an entry with the same user and id; it is atomic per
      call.
    - `get` returns None for a missing entry.
    - `search` considers only entries whose embedder identity equals
      `embedder`, raises `PermanentAdapterError` when `len(vector)` differs
      from `embedder.dimensions`, or when `limit < 1` or `user_id` is blank.
      Hits are best first (ties broken by id) and at most `limit` long.
    - `list` returns matching entries ordered by creation time, then id.
    - `delete` and `delete_user` are idempotent: missing ids are not errors.
    - `count_stale` counts entries across all users whose embedder identity
      differs from `embedder`, so a model change is detectable.
    - Blocking vendor calls must not block the event loop.
    """

    async def upsert(self, entries: Sequence[IndexEntry]) -> None: ...

    async def get(self, user_id: str, entry_id: str) -> IndexEntry | None: ...

    async def search(
        self,
        user_id: str,
        vector: Vector,
        *,
        limit: int,
        filter: SearchFilter | None = None,
        embedder: EmbedderInfo,
    ) -> list[SearchHit]: ...

    async def list(self, user_id: str, filter: SearchFilter | None = None) -> list[IndexEntry]: ...

    async def delete(self, user_id: str, ids: Sequence[str]) -> None: ...

    async def delete_user(self, user_id: str) -> None: ...

    async def count_stale(self, embedder: EmbedderInfo) -> int: ...


class SkillStore(Protocol):
    """Port: persists learned skills; `Skill.name` is the identity.

    Contract every adapter must meet:

    - `save` replaces a skill with the same name.
    - `get` of a missing name returns None; `delete` of a missing name is not
      an error.
    - `list` returns skills ordered by name.
    - A name that could escape the store (path separator, `..`, absolute
      path, NUL) raises `PermanentAdapterError` on every method.
    """

    async def save(self, skill: Skill) -> None: ...

    async def get(self, name: str) -> Skill | None: ...

    async def list(self) -> list[Skill]: ...

    async def delete(self, name: str) -> None: ...


@dataclass(frozen=True, slots=True)
class TranscriptTurn:
    """One conversation turn to summarize. Tool activity is not representable."""

    role: Literal["user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise DomainError(f"invalid transcript role: {self.role!r}")
        _require_text(self.content, "transcript content")


@dataclass(frozen=True, slots=True)
class FactCandidate:
    """A fact proposed by the summarizer; domain rules decide supersede and dedupe."""

    text: str
    profile_key: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.text, "fact candidate text")
        if self.profile_key is not None:
            _require_text(self.profile_key, "profile key")


class Summarizer(Protocol):
    """Port: condenses conversations and episodes with a model.

    Contract every adapter must meet:

    - `summarize` raises `PermanentAdapterError` for an empty sequence and
      returns non-blank text otherwise.
    - `distill` returns an empty list for an empty sequence without calling
      the vendor; every candidate has non-blank text.
    - It neither stores nor deduplicates; domain rules and use cases do.
    - Error text never contains transcript content.
    """

    async def summarize(self, turns: Sequence[TranscriptTurn]) -> str: ...

    async def distill(self, episodes: Sequence[Episode]) -> list[FactCandidate]: ...
