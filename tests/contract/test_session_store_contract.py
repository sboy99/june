"""One contract suite run against every `SessionStore` adapter (SHIP-325)."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from june.conversation import Session, SessionStore, Turn
from june.conversation.adapters.in_memory import InMemorySessionStore
from june.conversation.adapters.sqlite import SqliteSessionStore
from june.shared import PermanentAdapterError

pytestmark = pytest.mark.contract

T0 = datetime(2026, 1, 1, tzinfo=UTC)

FACTORIES: list[tuple[str, Callable[[Path], SessionStore]]] = [
    ("in_memory", lambda tmp: InMemorySessionStore()),
    ("sqlite", lambda tmp: SqliteSessionStore(tmp / "sessions.db")),
]


def session(session_id: str = "s1", user: str = "u1", minutes: int = 0, turns: int = 0) -> Session:
    result = Session.start(user, session_id, T0 + timedelta(minutes=minutes))
    for n in range(turns):
        result = result.with_turn(Turn(f"q{n}", f"a{n}", T0 + timedelta(minutes=minutes + n)))
    return result


@pytest.fixture(params=[pytest.param(f, id=name) for name, f in FACTORIES])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> SessionStore:
    return request.param(tmp_path)


async def test_save_then_get_round_trips_turns_in_order(store):
    await store.save(session(turns=3))

    assert await store.get("s1") == session(turns=3)


async def test_get_of_a_missing_session_returns_none(store):
    assert await store.get("missing") is None


async def test_save_replaces_the_session_with_the_same_id(store):
    await store.save(session(turns=3))
    await store.save(session(turns=1))

    assert await store.get("s1") == session(turns=1)


async def test_list_for_user_returns_only_that_users_sessions_oldest_first(store):
    await store.save(session("late", "u1", minutes=10))
    await store.save(session("early", "u1", minutes=1))
    await store.save(session("other", "u2", minutes=5))

    listed = await store.list_for_user("u1")

    assert [s.id for s in listed] == ["early", "late"]


async def test_list_for_user_without_sessions_is_empty(store):
    assert await store.list_for_user("nobody") == []


async def test_delete_removes_the_session_and_is_idempotent(store):
    await store.save(session(turns=2))

    await store.delete("s1")
    await store.delete("s1")

    assert await store.get("s1") is None


async def test_saved_sessions_are_not_changed_by_later_saves_of_others(store):
    await store.save(session("a", turns=2))
    await store.save(session("b", turns=1))

    assert await store.get("a") == session("a", turns=2)


@pytest.mark.parametrize("blank", ["", "  "])
async def test_blank_ids_raise_permanent_adapter_error(store, blank):
    with pytest.raises(PermanentAdapterError):
        await store.get(blank)
    with pytest.raises(PermanentAdapterError):
        await store.list_for_user(blank)
    with pytest.raises(PermanentAdapterError):
        await store.delete(blank)


async def test_sqlite_sessions_survive_reopening_the_file(tmp_path):
    path = tmp_path / "sessions.db"
    first = SqliteSessionStore(path)
    await first.save(session(turns=2))
    first.close()

    second = SqliteSessionStore(path)

    assert await second.get("s1") == session(turns=2)
    second.close()


async def test_sqlite_corrupt_row_raises_permanent_adapter_error(tmp_path):
    path = tmp_path / "sessions.db"
    store = SqliteSessionStore(path)
    await store.save(session(turns=1))
    store.close()
    conn = sqlite3.connect(path)
    conn.execute("UPDATE turns SET created_at = 'not-a-date'")
    conn.commit()
    conn.close()

    with pytest.raises(PermanentAdapterError):
        await SqliteSessionStore(path).get("s1")
