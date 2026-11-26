"""One contract suite run against every `VectorIndex` adapter (SHIP-324)."""

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from june.memory import EmbedderInfo, IndexEntry, SearchFilter, VectorIndex
from june.memory.adapters.sqlite_index import SqliteVectorIndex
from june.memory.domain import Episode, EpisodeStatus, Fact
from june.shared import PermanentAdapterError

pytestmark = pytest.mark.contract

T0 = datetime(2026, 1, 1, tzinfo=UTC)
EMB = EmbedderInfo("emb", "1", 3)
OTHER = EmbedderInfo("emb", "2", 3)
QUERY = (1.0, 0.0, 0.0)

FACTORIES: list[tuple[str, Callable[[Path], VectorIndex]]] = [
    ("sqlite-memory", lambda tmp: SqliteVectorIndex(":memory:")),
    ("sqlite-file", lambda tmp: SqliteVectorIndex(tmp / "memory.db")),
]


def fact(fid: str, user: str = "u1", age: int = 0, **extra) -> Fact:
    return Fact(
        id=fid,
        user_id=user,
        text=f"text {fid}",
        source="chat",
        created_at=T0 + timedelta(seconds=age),
        **extra,
    )


def episode(eid: str, user: str = "u1", age: int = 0, **extra) -> Episode:
    return Episode(
        id=eid, user_id=user, summary=f"sum {eid}", created_at=T0 + timedelta(seconds=age), **extra
    )


def entry(item, vector=QUERY, embedder=EMB) -> IndexEntry:
    return IndexEntry(item=item, vector=vector, embedder=embedder)


@pytest.fixture(params=[pytest.param(f, id=name) for name, f in FACTORIES])
async def index(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[VectorIndex]:
    adapter = request.param(tmp_path)
    yield adapter
    adapter.close()


async def test_get_returns_what_was_stored_and_none_when_missing(index):
    await index.upsert([entry(fact("f1"))])

    assert (await index.get("u1", "f1")).item == fact("f1")
    assert await index.get("u1", "nope") is None


async def test_upsert_replaces_an_entry_with_the_same_user_and_id(index):
    await index.upsert([entry(fact("f1"))])
    await index.upsert([entry(fact("f1", superseded_by="f2"))])

    assert (await index.get("u1", "f1")).item.superseded_by == "f2"
    assert len(await index.list("u1")) == 1


async def test_upsert_stores_every_entry_of_a_batch(index):
    await index.upsert([entry(fact("a")), entry(episode("b")), entry(fact("c"))])

    assert [e.id for e in await index.list("u1")] == ["a", "b", "c"]


async def test_users_never_see_each_others_entries(index):
    await index.upsert([entry(fact("f1")), entry(fact("f1", user="u2"))])

    assert (await index.get("u2", "f1")).user_id == "u2"
    assert [h.entry.user_id for h in await index.search("u1", QUERY, limit=5, embedder=EMB)] == [
        "u1"
    ]
    assert [e.user_id for e in await index.list("u1")] == ["u1"]
    await index.delete("u1", ["f1"])
    assert await index.get("u2", "f1") is not None
    await index.delete_user("u1")
    assert await index.get("u2", "f1") is not None


async def test_search_is_best_first_ties_by_id_and_limited(index):
    await index.upsert(
        [
            entry(fact("far"), (0.0, 1.0, 0.0)),
            entry(fact("b")),
            entry(fact("a")),
            entry(fact("mid"), (1.0, 1.0, 0.0)),
        ]
    )

    hits = await index.search("u1", QUERY, limit=3, embedder=EMB)

    assert [h.entry.id for h in hits] == ["a", "b", "mid"]
    assert all(-1.0 - 1e-6 <= h.score <= 1.0 + 1e-6 for h in hits)


async def test_search_considers_only_entries_of_the_same_embedder(index):
    await index.upsert([entry(fact("old"), embedder=OTHER), entry(fact("new"))])

    hits = await index.search("u1", QUERY, limit=5, embedder=EMB)

    assert [h.entry.id for h in hits] == ["new"]


async def test_search_with_wrong_vector_length_is_permanent(index):
    with pytest.raises(PermanentAdapterError):
        await index.search("u1", (1.0, 0.0), limit=1, embedder=EMB)


async def test_filters_narrow_search_and_list(index):
    done = episode("done", status=EpisodeStatus.CONSOLIDATED)
    await index.upsert(
        [
            entry(fact("live")),
            entry(fact("old", superseded_by="live")),
            entry(episode("pend")),
            entry(done),
        ]
    )

    facts = SearchFilter(kind="fact")
    active = SearchFilter(kind="fact", active_only=True)
    pending = SearchFilter(kind="episode", episode_status=EpisodeStatus.PENDING)

    assert [e.id for e in await index.list("u1", facts)] == ["live", "old"]
    assert [e.id for e in await index.list("u1", active)] == ["live"]
    assert [e.id for e in await index.list("u1", pending)] == ["pend"]
    hits = await index.search("u1", QUERY, limit=9, filter=active, embedder=EMB)
    assert [h.entry.id for h in hits] == ["live"]


async def test_list_is_ordered_by_creation_time_then_id(index):
    await index.upsert([entry(fact("b", age=5)), entry(fact("c", age=1)), entry(fact("a", age=5))])

    assert [e.id for e in await index.list("u1")] == ["c", "a", "b"]


async def test_deletes_are_idempotent(index):
    await index.upsert([entry(fact("f1")), entry(fact("f2"))])

    await index.delete("u1", ["f1", "missing"])
    await index.delete("u1", ["f1"])
    assert [e.id for e in await index.list("u1")] == ["f2"]

    await index.delete_user("u1")
    await index.delete_user("u1")
    assert await index.list("u1") == []


async def test_count_stale_counts_other_embedders_across_users(index):
    await index.upsert(
        [
            entry(fact("a"), embedder=OTHER),
            entry(fact("b", user="u2"), embedder=OTHER),
            entry(fact("c")),
        ]
    )

    assert await index.count_stale(EMB) == 2
    assert await index.count_stale(OTHER) == 1


async def test_updated_entry_keeps_its_vector(index):
    original = entry(fact("f1"), (0.0, 1.0, 0.0))
    await index.upsert([original])

    await index.upsert([replace(original, item=original.item.mark_superseded("f2"))])

    assert (await index.get("u1", "f1")).vector == (0.0, 1.0, 0.0)


@pytest.mark.parametrize("user", ["", "   "])
async def test_blank_user_is_permanent_on_every_method(index, user):
    calls = [
        index.get(user, "x"),
        index.search(user, QUERY, limit=1, embedder=EMB),
        index.list(user),
        index.delete(user, ["x"]),
        index.delete_user(user),
    ]
    for call in calls:
        with pytest.raises(PermanentAdapterError):
            await call


@pytest.mark.parametrize("limit", [0, -1])
async def test_search_limit_below_one_is_permanent(index, limit):
    with pytest.raises(PermanentAdapterError):
        await index.search("u1", QUERY, limit=limit, embedder=EMB)
