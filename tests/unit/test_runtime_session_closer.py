import asyncio
from datetime import UTC, datetime

import pytest

from june.conversation import Session, Turn
from june.memory import TranscriptTurn
from june.runtime import SessionCloser
from june.shared import DomainError, ToolError

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class Recorder:
    """Fake for both memory use cases; records calls in one shared log."""

    def __init__(self, log, name, fail=None, gate=None):
        self.log, self.name, self.fail, self.gate = log, name, fail, gate

    async def execute(self, user_id, turns=None):
        if self.gate is not None:
            await self.gate.wait()
        self.log.append((self.name, user_id, turns))
        if self.fail is not None:
            raise self.fail


def session(user_id="u1", turns=1) -> Session:
    made = tuple(Turn(f"q{n}", f"a{n}", NOW) for n in range(turns))
    return Session(id=f"s-{user_id}", user_id=user_id, created_at=NOW, turns=made)


def closer(every=2, remember_fail=None, consolidate_fail=None, gate=None):
    log: list = []
    built = SessionCloser(
        Recorder(log, "remember", remember_fail, gate),
        Recorder(log, "consolidate", consolidate_fail),
        every_n_sessions=every,
    )
    return built, log


async def test_end_session_returns_before_the_background_work_finishes():
    gate = asyncio.Event()
    built, log = closer(gate=gate)

    built.end_session(session())

    assert log == []
    gate.set()
    await built.drain()
    assert [entry[0] for entry in log] == ["remember"]


async def test_the_transcript_is_stored_in_turn_order():
    built, log = closer()

    built.end_session(session(turns=2))
    await built.drain()

    assert log == [
        (
            "remember",
            "u1",
            [
                TranscriptTurn("user", "q0"),
                TranscriptTurn("assistant", "a0"),
                TranscriptTurn("user", "q1"),
                TranscriptTurn("assistant", "a1"),
            ],
        )
    ]


async def test_a_session_without_turns_does_nothing_and_is_not_counted():
    built, log = closer(every=1)

    built.end_session(session(turns=0))
    await built.drain()

    assert log == []


async def test_consolidation_runs_after_every_nth_session_after_the_episode_is_stored():
    built, log = closer(every=2)

    for _ in range(4):
        built.end_session(session())
    await built.drain()

    assert [entry[0] for entry in log] == [
        "remember",
        "remember",
        "consolidate",
        "remember",
        "remember",
        "consolidate",
    ]
    assert log[2][1] == "u1"


async def test_counts_are_kept_per_user():
    built, log = closer(every=2)

    built.end_session(session("u1"))
    built.end_session(session("u2"))
    await built.drain()

    assert "consolidate" not in [entry[0] for entry in log]


async def test_a_failed_episode_is_not_counted_and_does_not_consolidate():
    built, log = closer(every=1, remember_fail=ToolError("boom"))

    built.end_session(session())
    await built.drain()

    assert [entry[0] for entry in log] == ["remember"]


async def test_a_failed_consolidation_does_not_stop_the_next_trigger():
    built, log = closer(every=1, consolidate_fail=ToolError("boom"))

    built.end_session(session())
    built.end_session(session())
    await built.drain()

    assert [entry[0] for entry in log].count("consolidate") == 2


async def test_unexpected_exceptions_are_contained_and_logged(caplog):
    built, _ = closer(every=1, remember_fail=RuntimeError("bug"))

    built.end_session(session())
    await built.drain()

    assert any(record.exc_info for record in caplog.records)


def test_every_n_sessions_below_one_is_rejected():
    with pytest.raises(DomainError):
        closer(every=0)
