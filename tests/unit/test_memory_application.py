from datetime import UTC, datetime, timedelta

import pytest

from june.memory import Forget, Recall, RememberEpisode, RememberFact
from june.memory.adapters.hashing_embedder import HashingEmbedder
from june.memory.adapters.sqlite_index import SqliteVectorIndex
from june.memory.domain import EpisodeStatus, Fact
from june.memory.ports import SearchFilter
from june.shared import DomainError, FixedClock, PermanentAdapterError, TransientAdapterError

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 1, tzinfo=UTC)


class CountingIds:
    def __init__(self):
        self.count = 0

    def new_id(self):
        self.count += 1
        return f"id{self.count}"


class SpyEmbedder(HashingEmbedder):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        return await super().embed(texts)


@pytest.fixture
def clock():
    return FixedClock(NOW)


@pytest.fixture
def embedder():
    return SpyEmbedder()


@pytest.fixture
async def index():
    adapter = SqliteVectorIndex(":memory:")
    yield adapter
    adapter.close()


@pytest.fixture
def ids():
    return CountingIds()


@pytest.fixture
def remember_fact(index, embedder, clock, ids):
    return RememberFact(index, embedder, clock, ids)


@pytest.fixture
def remember_episode(index, embedder, clock, ids):
    return RememberEpisode(index, embedder, clock, ids)


@pytest.fixture
def recall(index, embedder, clock):
    return Recall(index, embedder, clock)


async def stored_facts(index, user="u1"):
    return [e.item for e in await index.list(user, SearchFilter(kind="fact"))]


# --- remember fact ---------------------------------------------------------------------------


async def test_remember_fact_stores_and_returns_the_fact(remember_fact, index):
    fact = await remember_fact.execute("u1", "likes green tea", "chat", profile_key="drink")

    assert fact == Fact(
        id="id1",
        user_id="u1",
        text="likes green tea",
        source="chat",
        created_at=NOW,
        profile_key="drink",
    )
    assert await stored_facts(index) == [fact]


async def test_duplicate_text_returns_existing_and_writes_nothing(remember_fact, index, embedder):
    first = await remember_fact.execute("u1", "Likes  green tea", "chat")
    calls = embedder.calls

    again = await remember_fact.execute("u1", "likes green TEA", "chat")

    assert again == first
    assert embedder.calls == calls
    assert len(await stored_facts(index)) == 1


async def test_same_text_for_another_user_is_not_a_duplicate(remember_fact, index):
    await remember_fact.execute("u1", "likes tea", "chat")
    await remember_fact.execute("u2", "likes tea", "chat")

    assert len(await stored_facts(index, "u1")) == len(await stored_facts(index, "u2")) == 1


async def test_profile_key_supersedes_the_old_fact_and_keeps_its_vector(remember_fact, index):
    old = await remember_fact.execute("u1", "lives in Paris", "chat", profile_key="city")
    old_entry = await index.get("u1", old.id)

    new = await remember_fact.execute("u1", "lives in Berlin", "chat", profile_key="City ")

    updated = await index.get("u1", old.id)
    assert updated.item == old.mark_superseded(new.id)
    assert updated.vector == old_entry.vector
    assert (await index.get("u1", new.id)).item.is_active


async def test_supersede_ignores_other_users_and_other_keys(remember_fact, index):
    other_user = await remember_fact.execute("u2", "lives in Paris", "chat", profile_key="city")
    other_key = await remember_fact.execute("u1", "likes tea", "chat", profile_key="drink")

    await remember_fact.execute("u1", "lives in Berlin", "chat", profile_key="city")

    assert (await index.get("u2", other_user.id)).item.is_active
    assert (await index.get("u1", other_key.id)).item.is_active


@pytest.mark.parametrize(
    "args", [("", "text", "chat"), ("u1", " ", "chat"), ("u1", "text", ""), ("  ", "text", "chat")]
)
async def test_invalid_fact_input_fails_before_any_embedding(remember_fact, embedder, args):
    with pytest.raises(DomainError):
        await remember_fact.execute(*args)

    assert embedder.calls == 0


# --- remember episode ------------------------------------------------------------------------


async def test_remember_episode_stores_a_pending_episode(remember_episode, index):
    episode = await remember_episode.execute("u1", "we planned a trip")

    assert (episode.id, episode.created_at, episode.status) == ("id1", NOW, EpisodeStatus.PENDING)
    assert [e.item for e in await index.list("u1", SearchFilter(kind="episode"))] == [episode]


@pytest.mark.parametrize("args", [("u1", " "), ("", "summary")])
async def test_invalid_episode_input_fails_before_any_embedding(remember_episode, embedder, args):
    with pytest.raises(DomainError):
        await remember_episode.execute(*args)

    assert embedder.calls == 0


# --- recall ----------------------------------------------------------------------------------


async def test_recall_returns_best_match_first_with_scores(remember_fact, recall):
    await remember_fact.execute("u1", "likes green tea", "chat")
    await remember_fact.execute("u1", "mortgage interest rates", "chat")

    [top, *rest] = await recall.execute("u1", "green tea")

    assert top.item.text == "likes green tea"
    assert top.similarity > 0 and top.recency == 1.0
    assert top.score == pytest.approx(top.similarity * top.recency)
    assert all(m.item.text != "mortgage interest rates" for m in rest)


async def test_recall_excludes_superseded_facts(remember_fact, recall):
    await remember_fact.execute("u1", "lives in Paris", "chat", profile_key="city")
    await remember_fact.execute("u1", "lives in Berlin", "chat", profile_key="city")

    texts = [m.item.text for m in await recall.execute("u1", "lives in")]

    assert texts == ["lives in Berlin"]


async def test_recall_is_scoped_to_the_user(remember_fact, recall):
    await remember_fact.execute("u2", "likes green tea", "chat")

    assert await recall.execute("u1", "green tea") == []


async def test_newer_memory_beats_older_with_equal_similarity(remember_fact, recall, clock):
    await remember_fact.execute("u1", "likes tea a", "chat")
    old_id = "id1"
    clock.advance(timedelta(days=90))
    await remember_fact.execute("u1", "likes tea b", "chat")

    memories = await recall.execute("u1", "likes tea")

    assert [m.item.id for m in memories][0] != old_id
    assert memories[0].recency > memories[1].recency


async def test_recency_can_lift_a_less_similar_newer_memory(remember_fact, recall, clock):
    await remember_fact.execute("u1", "green tea", "chat")
    clock.advance(timedelta(days=365))
    await remember_fact.execute("u1", "green tea and coffee", "chat")

    memories = await recall.execute("u1", "green tea", limit=1)

    assert memories[0].item.text == "green tea and coffee"


async def test_recall_can_be_restricted_to_a_kind(remember_fact, remember_episode, recall):
    await remember_fact.execute("u1", "likes green tea", "chat")
    await remember_episode.execute("u1", "talked about green tea")

    facts = await recall.execute("u1", "green tea", kind="fact")
    episodes = await recall.execute("u1", "green tea", kind="episode")

    assert [m.item.text for m in facts] == ["likes green tea"]
    assert [m.item.summary for m in episodes] == ["talked about green tea"]


async def test_recall_respects_limit_and_min_similarity(remember_fact, recall):
    for text in ("green tea one", "green tea two", "green tea three"):
        await remember_fact.execute("u1", text, "chat")

    assert len(await recall.execute("u1", "green tea", limit=2)) == 2
    assert await recall.execute("u1", "green tea", min_similarity=1.1) == []


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": -1}])
async def test_invalid_recall_limit_is_rejected(recall, kwargs):
    with pytest.raises(DomainError):
        await recall.execute("u1", "x", **kwargs)


@pytest.mark.parametrize("args", [("u1", " "), ("", "x")])
async def test_blank_recall_input_is_rejected_before_embedding(recall, embedder, args):
    with pytest.raises(DomainError):
        await recall.execute(*args)

    assert embedder.calls == 0


# --- forget ----------------------------------------------------------------------------------


async def test_forget_by_ids_is_idempotent_and_scoped(remember_fact, index):
    mine = await remember_fact.execute("u1", "a fact", "chat")
    theirs = await remember_fact.execute("u2", "a fact", "chat")
    forget = Forget(index)

    await forget.by_ids("u1", [mine.id, "missing"])
    await forget.by_ids("u1", [mine.id])
    await forget.by_ids("u1", [])

    assert await index.get("u1", mine.id) is None
    assert await index.get("u2", theirs.id) is not None


async def test_forget_everything_removes_only_that_user(remember_fact, remember_episode, index):
    await remember_fact.execute("u1", "a fact", "chat")
    await remember_episode.execute("u1", "an episode")
    await remember_fact.execute("u2", "a fact", "chat")

    await Forget(index).everything("u1")

    assert await index.list("u1") == []
    assert len(await index.list("u2")) == 1


# --- errors ----------------------------------------------------------------------------------


@pytest.mark.parametrize("error", [TransientAdapterError("t"), PermanentAdapterError("p")])
async def test_adapter_errors_pass_through_unchanged(clock, error):
    class Failing(HashingEmbedder):
        async def embed(self, texts):
            raise error

    index = SqliteVectorIndex(":memory:")
    try:
        with pytest.raises(type(error)) as caught:
            await RememberFact(index, Failing(), clock, CountingIds()).execute("u1", "t", "chat")
        assert caught.value is error
        with pytest.raises(type(error)):
            await Recall(index, Failing(), clock).execute("u1", "q")
    finally:
        index.close()
