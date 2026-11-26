"""`SessionStore` adapter on SQLite: one connection, a lock, work in a worker thread."""

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from june.conversation.session import Session, Turn
from june.shared import AdapterError, DomainError, PermanentAdapterError, TransientAdapterError
from june.shared.helpers import require_adapter_text

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id, created_at, id);
CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    user_message TEXT NOT NULL,
    reply TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, position)
);
"""
_BUSY_MARKERS = ("locked", "busy")


def _translate(exc: sqlite3.Error) -> AdapterError:
    text = f"sqlite session store failed: {type(exc).__name__}"
    if isinstance(exc, sqlite3.OperationalError) and any(
        marker in str(exc).lower() for marker in _BUSY_MARKERS
    ):
        return TransientAdapterError(text, cause=exc)
    return PermanentAdapterError(text, cause=exc)


def _load(conn: sqlite3.Connection, row: sqlite3.Row) -> Session:
    turn_rows = conn.execute(
        "SELECT user_message, reply, created_at FROM turns WHERE session_id = ? ORDER BY position",
        (row["id"],),
    ).fetchall()
    try:
        return Session(
            id=row["id"],
            user_id=row["user_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            turns=tuple(
                Turn(t["user_message"], t["reply"], datetime.fromisoformat(t["created_at"]))
                for t in turn_rows
            ),
        )
    except (ValueError, TypeError, DomainError) as exc:
        raise PermanentAdapterError("stored session is corrupt", cause=exc) from exc


def _write(conn: sqlite3.Connection, session: Session) -> None:
    conn.execute("DELETE FROM sessions WHERE id = ?", (session.id,))
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?)",
        (session.id, session.user_id, session.created_at.isoformat()),
    )
    conn.executemany(
        "INSERT INTO turns VALUES (?,?,?,?,?)",
        [
            (session.id, position, t.user_message, t.reply, t.created_at.isoformat())
            for position, t in enumerate(session.turns)
        ],
    )


class SqliteSessionStore:
    """Persists sessions and their turns in a SQLite file."""

    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        try:
            self._conn = sqlite3.connect(str(path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(_SCHEMA)
        except sqlite3.Error as exc:
            raise _translate(exc) from exc

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    async def save(self, session: Session) -> None:
        await self._run(lambda conn: _write(conn, session))

    async def get(self, session_id: str) -> Session | None:
        require_adapter_text(session_id, "session id")

        def read(conn: sqlite3.Connection) -> Session | None:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return None if row is None else _load(conn, row)

        return await self._run(read)

    async def list_for_user(self, user_id: str) -> list[Session]:
        require_adapter_text(user_id, "user id")

        def read(conn: sqlite3.Connection) -> list[Session]:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at, id", (user_id,)
            ).fetchall()
            return [_load(conn, row) for row in rows]

        return await self._run(read)

    async def delete(self, session_id: str) -> None:
        require_adapter_text(session_id, "session id")
        await self._run(
            lambda conn: conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        )

    async def _run[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        return await asyncio.to_thread(self._run_locked, work)

    def _run_locked[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        with self._lock:
            try:
                with self._conn:
                    return work(self._conn)
            except sqlite3.Error as exc:
                raise _translate(exc) from exc
