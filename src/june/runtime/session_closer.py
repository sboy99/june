"""Session closer: memory work when a Session ends, off the reply path.

`end_session` schedules a background task and returns at once. The task stores
the transcript as a pending Episode and, every N ended sessions of a user,
runs Consolidation. Failures are logged and never reach the caller.
"""

import asyncio
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from june.conversation import Session
from june.memory import ConsolidationResult, Episode, TranscriptTurn
from june.observability import get_logger
from june.shared import AgentError, DomainError

DEFAULT_EVERY_N_SESSIONS = 3

_log = get_logger(__name__)


class ConversationRemembering(Protocol):
    """Matches `RememberConversation`: store a transcript as a pending Episode."""

    async def execute(self, user_id: str, turns: Sequence[TranscriptTurn]) -> Episode: ...


class Consolidating(Protocol):
    """Matches `Consolidate`: turn a user's pending Episodes into Facts."""

    async def execute(self, user_id: str) -> ConsolidationResult: ...


def _transcript(session: Session) -> list[TranscriptTurn]:
    return [
        part
        for turn in session.turns
        for part in (
            TranscriptTurn("user", turn.user_message),
            TranscriptTurn("assistant", turn.reply),
        )
    ]


class SessionCloser:
    """Stores ended Sessions as Episodes and triggers Consolidation every N of them."""

    def __init__(
        self,
        remember_conversation: ConversationRemembering,
        consolidate: Consolidating,
        every_n_sessions: int = DEFAULT_EVERY_N_SESSIONS,
    ) -> None:
        if every_n_sessions < 1:
            raise DomainError("every_n_sessions must be at least 1")
        self._remember = remember_conversation
        self._consolidate = consolidate
        self._every_n = every_n_sessions
        self._ended: Counter[str] = Counter()
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def end_session(self, session: Session) -> None:
        """Schedule the memory work for `session` and return immediately."""
        if not session.turns:
            return
        task = asyncio.get_running_loop().create_task(self._close(session))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait for all scheduled work to finish."""
        while self._tasks:
            await asyncio.gather(*self._tasks)

    async def _close(self, session: Session) -> None:
        lock = self._locks.setdefault(session.user_id, asyncio.Lock())
        async with lock:
            try:
                await self._remember.execute(session.user_id, _transcript(session))
                self._ended[session.user_id] += 1
                if self._ended[session.user_id] % self._every_n == 0:
                    await self._consolidate.execute(session.user_id)
            except AgentError as exc:
                _log.warning("session close failed: %s", exc.code)
            except Exception:
                _log.exception("session close raised an unexpected exception")
