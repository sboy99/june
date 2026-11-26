import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from june.memory import EmbedderInfo, IndexEntry, SearchFilter, VectorIndex
from june.memory.adapters.sqlite_index import SqliteVectorIndex
from june.memory.domain import Episode, EpisodeStatus, Fact
from june.shared import PermanentAdapterError

pytestmark = pytest.mark.unit

EMB = EmbedderInfo("hashing", "1", 3)
OTHER = EmbedderInfo("hashing", "2", 3)
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def fact(id, user="u1", minutes=0, **kw):
    return Fact(
        id=id,
        user_id=user,
        text=f"text {id}",
        source="chat",
        created_at=T0 + timedelta(minutes=minutes),
        **kw,
    )


def episode(id, user="u1", minutes=0, **kw):
    return Episode(
        id=id,
        user_id=user,
        summary=f"summary {id}",
        created_at=T0 + timedelta(minutes=minutes),
        **kw,
    )


def entry(item, vector=(1.0, 0.0, 0.0), embedder=EMB):
    return IndexEntry(item=item, vector=vector, embedder=embedder)


@pytest.fixture
async def index():
    adapter = SqliteVectorIndex(":memory:")
    yield adapter
    adapter.close()


async def test_upsert_then_get_round_trips_a_fact(index: VectorIndex):
    item = fact("f1", profile_key="diet", superseded_by="f2")

    await index.upsert([entry(item, (0.5, 0.5, 0.0))])

    assert await index.get("u1", "f1") == entry(item, (0.5, 0.5, 0.0))


async def test_episode_round_trips_with_status(index):
    item = episode("e1", status=EpisodeStatus.CONSOLIDATED)

    await index.upsert([entry(item)])

    assert (await index.get("u1", "e1")).item == item


async def test_get_missing_or_other_user_returns_none(index):
    await index.upsert([entry(fact("f1"))])

    assert await index.get("u1", "nope") is None
    assert await index.get("u2", "f1") is None


async def test_upsert_replaces_same_id(index):
    await index.upsert([entry(fact("f1"))])
    await index.upsert([entry(fact("f1", superseded_by="f2"))])

    assert (await index.get("u1", "f1")).item.superseded_by == "f2"
    assert len(await index.list("u1")) == 1


async def test_same_id_for_different_users_does_not_collide(index):
    await index.upsert([entry(fact("f1", user="u1")), entry(fact("f1", user="u2"))])

    assert (await index.get("u1", "f1")).user_id == "u1"
    assert (await index.get("u2", "f1")).user_id == "u2"


async def test_search_ranks_by_cosine_best_first(index):
    await index.upsert(
        [
            entry(fact("far"), (0.0, 1.0, 0.0)),
            entry(fact("near"), (1.0, 0.1, 0.0)),
            entry(fact("mid"), (1.0, 1.0, 0.0)),
        ]
    )

    hits = await index.search("u1", (1.0, 0.0, 0.0), limit=3, embedder=EMB)

    assert [h.entry.id for h in hits] == ["near", "mid", "far"]
    assert hits[0].score > hits[1].score > hits[2].score
    assert hits[2].score == pytest.approx(0.0)


async def test_search_breaks_ties_by_id_and_honours_limit(index):
    await index.upsert([entry(fact("b")), entry(fact("a")), entry(fact("c"))])

    hits = await index.search("u1", (1.0, 0.0, 0.0), limit=2, embedder=EMB)

    assert [h.entry.id for h in hits] == ["a", "b"]


async def test_search_is_scoped_to_one_user(index):
    await index.upsert([entry(fact("mine")), entry(fact("theirs", user="u2"))])

    hits = await index.search("u1", (1.0, 0.0, 0.0), limit=5, embedder=EMB)

    assert [h.entry.id for h in hits] == ["mine"]


async def test_search_skips_entries_from_another_embedder(index):
    await index.upsert([entry(fact("old"), embedder=OTHER), entry(fact("new"))])

    hits = await index.search("u1", (1.0, 0.0, 0.0), limit=5, embedder=EMB)

    assert [h.entry.id for h in hits] == ["new"]


async def test_search_rejects_wrong_query_dimension(index):
    with pytest.raises(PermanentAdapterError):
        await index.search("u1", (1.0, 0.0), limit=1, embedder=EMB)


async def test_zero_query_vector_scores_zero(index):
    await index.upsert([entry(fact("f1"))])

    [hit] = await index.search("u1", (0.0, 0.0, 0.0), limit=1, embedder=EMB)

    assert hit.score == 0.0


@pytest.mark.parametrize("limit", [0, -1])
async def test_search_rejects_bad_limit(index, limit):
    with pytest.raises(PermanentAdapterError):
        await index.search("u1", (1.0, 0.0, 0.0), limit=limit, embedder=EMB)


@pytest.mark.parametrize("user", ["", "   "])
async def test_blank_user_is_rejected_everywhere(index, user):
    calls = [
        index.get(user, "x"),
        index.search(user, (1.0, 0.0, 0.0), limit=1, embedder=EMB),
        index.list(user),
        index.delete(user, ["x"]),
        index.delete_user(user),
    ]
    for call in calls:
        with pytest.raises(PermanentAdapterError):
            await call


async def test_filters_apply_to_search_and_list(index):
    await index.upsert(
        [
            entry(fact("active")),
            entry(fact("old", superseded_by="active")),
            entry(episode("pending")),
            entry(episode("done", status=EpisodeStatus.CONSOLIDATED)),
        ]
    )

    async def ids(flt):
        listed = [e.id for e in await index.list("u1", flt)]
        searched = [
            h.entry.id
            for h in await index.search("u1", (1.0, 0.0, 0.0), limit=10, filter=flt, embedder=EMB)
        ]
        assert sorted(listed) == sorted(searched)
        return sorted(listed)

    assert await ids(None) == ["active", "done", "old", "pending"]
    assert await ids(SearchFilter(kind="fact")) == ["active", "old"]
    assert await ids(SearchFilter(kind="episode")) == ["done", "pending"]
    assert await ids(SearchFilter(active_only=True)) == ["active", "done", "pending"]
    assert await ids(SearchFilter(episode_status=EpisodeStatus.PENDING)) == [
        "active",
        "old",
        "pending",
    ]
    assert await ids(SearchFilter(kind="episode", episode_status=EpisodeStatus.PENDING)) == [
        "pending"
    ]


async def test_list_orders_by_creation_time_then_id(index):
    await index.upsert(
        [
            entry(fact("b", minutes=5)),
            entry(fact("z", minutes=1)),
            entry(fact("a", minutes=5)),
        ]
    )

    assert [e.id for e in await index.list("u1")] == ["z", "a", "b"]


async def test_delete_is_idempotent_and_scoped(index):
    await index.upsert([entry(fact("f1")), entry(fact("f1", user="u2"))])

    await index.delete("u1", ["f1", "missing"])
    await index.delete("u1", ["f1"])
    await index.delete("u1", [])

    assert await index.get("u1", "f1") is None
    assert await index.get("u2", "f1") is not None


async def test_delete_user_removes_only_that_user(index):
    await index.upsert([entry(fact("a")), entry(fact("b", user="u2"))])

    await index.delete_user("u1")
    await index.delete_user("u1")

    assert await index.list("u1") == []
    assert len(await index.list("u2")) == 1


async def test_count_stale_spans_all_users(index):
    await index.upsert(
        [
            entry(fact("a"), embedder=OTHER),
            entry(fact("b", user="u2"), embedder=OTHER),
            entry(fact("c")),
        ]
    )

    assert await index.count_stale(EMB) == 2
    assert await index.count_stale(OTHER) == 1


async def test_data_persists_across_instances(tmp_path):
    path = tmp_path / "memory.db"
    first = SqliteVectorIndex(path)
    await first.upsert([entry(fact("f1"))])
    first.close()

    second = SqliteVectorIndex(path)
    try:
        assert await second.get("u1", "f1") is not None
    finally:
        second.close()


async def test_event_loop_stays_responsive_during_a_call(index):
    await index.upsert([entry(fact(f"f{i}")) for i in range(200)])
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0)
            ticks += 1

    task = asyncio.create_task(ticker())
    await index.search("u1", (1.0, 0.0, 0.0), limit=5, embedder=EMB)
    task.cancel()

    assert ticks > 0


async def test_sqlite_failures_become_permanent_adapter_errors(tmp_path):
    adapter = SqliteVectorIndex(tmp_path / "memory.db")
    adapter.close()

    with pytest.raises(PermanentAdapterError) as caught:
        await adapter.get("u1", "f1")

    assert "sqlite3" not in type(caught.value).__module__
