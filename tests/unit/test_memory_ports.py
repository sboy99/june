from collections.abc import Sequence
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from june.memory import (
    Embedder,
    EmbedderInfo,
    FactCandidate,
    IndexEntry,
    SearchFilter,
    SearchHit,
    SkillStore,
    Summarizer,
    TranscriptTurn,
    Vector,
    VectorIndex,
)
from june.memory.domain import Episode, EpisodeStatus, Fact, Skill
from june.shared import DomainError

pytestmark = pytest.mark.unit


def test_embedder_info_is_value_equal_and_hashable():
    a = EmbedderInfo(name="hash", version="1", dimensions=4)
    b = EmbedderInfo(name="hash", version="1", dimensions=4)

    assert a == b
    assert len({a, b}) == 1


@pytest.mark.parametrize("dimensions", [0, -1])
def test_embedder_info_rejects_non_positive_dimensions(dimensions):
    with pytest.raises(DomainError):
        EmbedderInfo(name="hash", version="1", dimensions=dimensions)


@pytest.mark.parametrize(("name", "version"), [("", "1"), ("hash", " ")])
def test_embedder_info_rejects_blank_name_or_version(name, version):
    with pytest.raises(DomainError):
        EmbedderInfo(name=name, version=version, dimensions=2)


def test_embedder_info_is_immutable():
    info = EmbedderInfo(name="hash", version="1", dimensions=2)

    with pytest.raises(FrozenInstanceError):
        info.name = "other"  # type: ignore[misc]


class FakeEmbedder:
    @property
    def info(self) -> EmbedderInfo:
        return EmbedderInfo(name="fake", version="1", dimensions=2)

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [(float(len(t)), 1.0) for t in texts]


async def test_fake_embedder_satisfies_port():
    embedder: Embedder = FakeEmbedder()

    vectors = await embedder.embed(["ab", "c"])

    assert vectors == [(2.0, 1.0), (1.0, 1.0)]
    assert embedder.info.dimensions == 2


NOW = datetime(2026, 1, 1, tzinfo=UTC)
INFO = EmbedderInfo(name="fake", version="1", dimensions=2)


def make_fact(fact_id="f1", user_id="u1", superseded_by=None) -> Fact:
    return Fact(
        id=fact_id,
        user_id=user_id,
        text="likes tea",
        source="user",
        created_at=NOW,
        superseded_by=superseded_by,
    )


def make_episode(episode_id="e1", user_id="u1") -> Episode:
    return Episode(id=episode_id, user_id=user_id, summary="talked", created_at=NOW)


def test_index_entry_exposes_id_user_and_kind_of_its_item():
    fact_entry = IndexEntry(item=make_fact(), vector=(1.0, 0.0), embedder=INFO)
    episode_entry = IndexEntry(item=make_episode(), vector=(1.0, 0.0), embedder=INFO)

    assert (fact_entry.id, fact_entry.user_id, fact_entry.kind) == ("f1", "u1", "fact")
    assert (episode_entry.id, episode_entry.user_id, episode_entry.kind) == ("e1", "u1", "episode")


def test_index_entry_rejects_vector_of_wrong_dimension():
    with pytest.raises(DomainError):
        IndexEntry(item=make_fact(), vector=(1.0,), embedder=INFO)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_index_entry_rejects_non_finite_values(bad):
    with pytest.raises(DomainError):
        IndexEntry(item=make_fact(), vector=(bad, 0.0), embedder=INFO)


def test_index_entry_is_value_equal_and_hashable():
    a = IndexEntry(item=make_fact(), vector=(1.0, 0.0), embedder=INFO)
    b = IndexEntry(item=make_fact(), vector=(1.0, 0.0), embedder=INFO)

    assert a == b
    assert len({a, b}) == 1


def test_search_filter_defaults_match_everything():
    default = SearchFilter()

    assert default.kind is None
    assert default.active_only is False
    assert default.episode_status is None


def test_search_filter_rejects_unknown_kind():
    with pytest.raises(DomainError):
        SearchFilter(kind="skill")  # type: ignore[arg-type]


def test_search_filter_rejects_unknown_episode_status():
    with pytest.raises(DomainError):
        SearchFilter(episode_status="done")  # type: ignore[arg-type]


def test_search_hit_rejects_score_outside_cosine_range():
    entry = IndexEntry(item=make_fact(), vector=(1.0, 0.0), embedder=INFO)

    assert SearchHit(entry=entry, score=-1.0).score == -1.0
    assert SearchHit(entry=entry, score=1.0000000002).score > 1.0
    with pytest.raises(DomainError):
        SearchHit(entry=entry, score=1.5)


class FakeIndex:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], IndexEntry] = {}

    async def upsert(self, entries: Sequence[IndexEntry]) -> None:
        for entry in entries:
            self.entries[(entry.user_id, entry.id)] = entry

    async def get(self, user_id: str, entry_id: str) -> IndexEntry | None:
        return self.entries.get((user_id, entry_id))

    async def search(
        self,
        user_id: str,
        vector: Vector,
        *,
        limit: int,
        filter: SearchFilter | None = None,
        embedder: EmbedderInfo,
    ) -> list[SearchHit]:
        return []

    async def list(self, user_id: str, filter: SearchFilter | None = None) -> list[IndexEntry]:
        return [e for (u, _), e in self.entries.items() if u == user_id]

    async def delete(self, user_id: str, ids: Sequence[str]) -> None:
        for entry_id in ids:
            self.entries.pop((user_id, entry_id), None)

    async def delete_user(self, user_id: str) -> None:
        self.entries = {k: v for k, v in self.entries.items() if k[0] != user_id}

    async def count_stale(self, embedder: EmbedderInfo) -> int:
        return sum(1 for e in self.entries.values() if e.embedder != embedder)


async def test_fake_index_satisfies_port():
    index: VectorIndex = FakeIndex()
    entry = IndexEntry(item=make_episode().mark_consolidated(), vector=(1.0, 0.0), embedder=INFO)

    await index.upsert([entry])

    assert await index.get("u1", "e1") == entry
    assert await index.count_stale(INFO) == 0
    assert entry.item.status == EpisodeStatus.CONSOLIDATED  # type: ignore[union-attr]


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_transcript_turn_accepts_user_and_assistant(role):
    assert TranscriptTurn(role=role, content="hi").role == role


@pytest.mark.parametrize(("role", "content"), [("tool", "x"), ("system", "x"), ("user", "  ")])
def test_transcript_turn_rejects_tool_activity_and_blank_content(role, content):
    with pytest.raises(DomainError):
        TranscriptTurn(role=role, content=content)  # type: ignore[arg-type]


def test_fact_candidate_requires_text_and_allows_optional_profile_key():
    assert FactCandidate(text="likes tea").profile_key is None
    assert FactCandidate(text="UTC", profile_key="timezone").profile_key == "timezone"
    with pytest.raises(DomainError):
        FactCandidate(text=" ")
    with pytest.raises(DomainError):
        FactCandidate(text="x", profile_key=" ")


class FakeSkillStore:
    def __init__(self) -> None:
        self.skills: dict[str, Skill] = {}

    async def save(self, skill: Skill) -> None:
        self.skills[skill.name] = skill

    async def get(self, name: str) -> Skill | None:
        return self.skills.get(name)

    async def list(self) -> list[Skill]:
        return [self.skills[n] for n in sorted(self.skills)]

    async def delete(self, name: str) -> None:
        self.skills.pop(name, None)


async def test_fake_skill_store_satisfies_port():
    store: SkillStore = FakeSkillStore()
    skill = Skill(name="brew", description="make tea", steps=("boil",), created_at=NOW)

    await store.save(skill)

    assert await store.get("brew") == skill
    assert await store.list() == [skill]
    assert await store.get("missing") is None


class FakeSummarizer:
    async def summarize(self, turns: Sequence[TranscriptTurn]) -> str:
        return " / ".join(t.content for t in turns)

    async def distill(self, episodes: Sequence[Episode]) -> list[FactCandidate]:
        return [FactCandidate(text=e.summary) for e in episodes]


async def test_fake_summarizer_satisfies_port():
    summarizer: Summarizer = FakeSummarizer()

    summary = await summarizer.summarize([TranscriptTurn(role="user", content="hi")])
    candidates = await summarizer.distill([make_episode()])

    assert summary == "hi"
    assert candidates == [FactCandidate(text="talked")]
