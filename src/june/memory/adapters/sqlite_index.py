"""`VectorIndex` adapter on SQLite: exact cosine search over one user's rows."""

import asyncio
import json
import math
import sqlite3
import threading
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from june.memory.domain import Episode, EpisodeStatus, Fact
from june.memory.ports import EmbedderInfo, IndexEntry, SearchFilter, SearchHit, Vector
from june.shared import AdapterError, DomainError, PermanentAdapterError, TransientAdapterError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    user_id TEXT NOT NULL,
    id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    superseded_by TEXT,
    status TEXT,
    item_json TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    embedder_name TEXT NOT NULL,
    embedder_version TEXT NOT NULL,
    embedder_dimensions INTEGER NOT NULL,
    PRIMARY KEY (user_id, id)
);
CREATE INDEX IF NOT EXISTS entries_user_kind ON entries (user_id, kind);
"""
_BUSY_MARKERS = ("locked", "busy")
_ListQuery = list[IndexEntry]


def _require_user(user_id: str) -> None:
    if not user_id.strip():
        raise PermanentAdapterError("user id must not be blank")


def _translate(exc: sqlite3.Error) -> AdapterError:
    text = f"sqlite index failed: {type(exc).__name__}"
    if isinstance(exc, sqlite3.OperationalError) and any(
        marker in str(exc).lower() for marker in _BUSY_MARKERS
    ):
        return TransientAdapterError(text, cause=exc)
    return PermanentAdapterError(text, cause=exc)


def _item_to_json(item: Fact | Episode) -> str:
    base: dict[str, Any] = {"id": item.id, "user_id": item.user_id}
    base["created_at"] = item.created_at.isoformat()
    if isinstance(item, Fact):
        base.update(
            text=item.text,
            source=item.source,
            profile_key=item.profile_key,
            superseded_by=item.superseded_by,
        )
    else:
        base.update(summary=item.summary, status=item.status.value)
    return json.dumps(base, ensure_ascii=False)


def _item_from_json(kind: str, raw: str) -> Fact | Episode:
    data = json.loads(raw)
    created_at = datetime.fromisoformat(data["created_at"])
    if kind == "fact":
        return Fact(
            id=data["id"],
            user_id=data["user_id"],
            text=data["text"],
            source=data["source"],
            created_at=created_at,
            profile_key=data["profile_key"],
            superseded_by=data["superseded_by"],
        )
    return Episode(
        id=data["id"],
        user_id=data["user_id"],
        summary=data["summary"],
        created_at=created_at,
        status=EpisodeStatus(data["status"]),
    )


def _row_to_entry(row: sqlite3.Row) -> IndexEntry:
    try:
        return IndexEntry(
            item=_item_from_json(row["kind"], row["item_json"]),
            vector=tuple(json.loads(row["vector_json"])),
            embedder=EmbedderInfo(
                name=row["embedder_name"],
                version=row["embedder_version"],
                dimensions=row["embedder_dimensions"],
            ),
        )
    except (ValueError, KeyError, TypeError, DomainError) as exc:
        raise PermanentAdapterError("stored index entry is corrupt", cause=exc) from exc


def _entry_to_params(entry: IndexEntry) -> tuple[Any, ...]:
    item = entry.item
    return (
        entry.user_id,
        entry.id,
        entry.kind,
        item.created_at.isoformat(),
        item.superseded_by if isinstance(item, Fact) else None,
        item.status.value if isinstance(item, Episode) else None,
        _item_to_json(item),
        json.dumps(list(entry.vector)),
        entry.embedder.name,
        entry.embedder.version,
        entry.embedder.dimensions,
    )


def _filter_sql(flt: SearchFilter | None) -> tuple[str, list[Any]]:
    flt = flt or SearchFilter()
    clauses: list[str] = []
    params: list[Any] = []
    if flt.kind is not None:
        clauses.append("kind = ?")
        params.append(flt.kind)
    if flt.active_only:
        clauses.append("(kind != 'fact' OR superseded_by IS NULL)")
    if flt.episode_status is not None:
        clauses.append("(kind != 'episode' OR status = ?)")
        params.append(flt.episode_status.value)
    return "".join(f" AND {clause}" for clause in clauses), params


def _write_many(conn: sqlite3.Connection, sql: str, rows: Sequence[tuple[Any, ...]]) -> None:
    conn.executemany(sql, rows)


def _cosine(a: Vector, b: Vector) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0.0:
        return 0.0
    score = sum(x * y for x, y in zip(a, b, strict=True)) / norm
    return max(-1.0, min(1.0, score))


class SqliteVectorIndex:
    """One SQLite connection guarded by a lock; every call runs in a worker thread."""

    def __init__(self, path: Path | str) -> None:
        self._lock = threading.Lock()
        try:
            self._conn = sqlite3.connect(str(path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
        except sqlite3.Error as exc:
            raise _translate(exc) from exc

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    async def upsert(self, entries: Sequence[IndexEntry]) -> None:
        rows = [_entry_to_params(entry) for entry in entries]
        sql = "INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        await self._run(lambda conn: _write_many(conn, sql, rows))

    async def get(self, user_id: str, entry_id: str) -> IndexEntry | None:
        _require_user(user_id)
        sql = "SELECT * FROM entries WHERE user_id = ? AND id = ?"
        rows = await self._run(lambda conn: conn.execute(sql, (user_id, entry_id)).fetchall())
        return _row_to_entry(rows[0]) if rows else None

    async def search(
        self,
        user_id: str,
        vector: Vector,
        *,
        limit: int,
        filter: SearchFilter | None = None,
        embedder: EmbedderInfo,
    ) -> list[SearchHit]:
        _require_user(user_id)
        if limit < 1:
            raise PermanentAdapterError("limit must be at least 1")
        if len(vector) != embedder.dimensions:
            raise PermanentAdapterError("query vector length must equal embedder dimensions")
        if not all(math.isfinite(x) for x in vector):
            raise PermanentAdapterError("query vector values must be finite")
        entries = await self._select(user_id, filter, embedder)
        hits = [SearchHit(entry=e, score=_cosine(vector, e.vector)) for e in entries]
        hits.sort(key=lambda hit: (-hit.score, hit.entry.id))
        return hits[:limit]

    async def list(self, user_id: str, filter: SearchFilter | None = None) -> _ListQuery:
        _require_user(user_id)
        return await self._select(user_id, filter, None)

    async def delete(self, user_id: str, ids: Sequence[str]) -> None:
        _require_user(user_id)
        rows = [(user_id, entry_id) for entry_id in ids]
        sql = "DELETE FROM entries WHERE user_id = ? AND id = ?"
        await self._run(lambda conn: _write_many(conn, sql, rows))

    async def delete_user(self, user_id: str) -> None:
        _require_user(user_id)
        await self._run(
            lambda conn: _write_many(conn, "DELETE FROM entries WHERE user_id = ?", [(user_id,)])
        )

    async def count_stale(self, embedder: EmbedderInfo) -> int:
        sql = (
            "SELECT COUNT(*) FROM entries WHERE NOT (embedder_name = ? "
            "AND embedder_version = ? AND embedder_dimensions = ?)"
        )
        params = (embedder.name, embedder.version, embedder.dimensions)
        rows = await self._run(lambda conn: conn.execute(sql, params).fetchall())
        return int(rows[0][0])

    async def _select(
        self, user_id: str, flt: SearchFilter | None, embedder: EmbedderInfo | None
    ) -> _ListQuery:
        extra, params = _filter_sql(flt)
        sql = "SELECT * FROM entries WHERE user_id = ?"
        args: list[Any] = [user_id]
        if embedder is not None:
            sql += " AND embedder_name = ? AND embedder_version = ? AND embedder_dimensions = ?"
            args += [embedder.name, embedder.version, embedder.dimensions]
        sql += extra + " ORDER BY created_at, id"
        rows = await self._run(lambda conn: conn.execute(sql, [*args, *params]).fetchall())
        return [_row_to_entry(row) for row in rows]

    async def _run[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        return await asyncio.to_thread(self._run_locked, work)

    def _run_locked[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        with self._lock:
            try:
                with self._conn:
                    return work(self._conn)
            except sqlite3.Error as exc:
                raise _translate(exc) from exc
