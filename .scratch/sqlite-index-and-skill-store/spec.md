# SQLite index and file skill store adapters (SHIP-321, P2.4)

Status: ready-for-agent
Source: Linear SHIP-321, milestone "Phase 2: Memory"
Branch: `contactsagarbera/ship-321-p24-sqlite-index-and-file-skill` (stacked on SHIP-320)

## Problem Statement

`VectorIndex` and `SkillStore` have written contracts and no implementation. Remember, recall and forget (P2.5) and consolidation (P2.6) need real storage that survives a restart.

## Solution

Two adapters in `june.memory.adapters`:

- `SqliteVectorIndex`: stores Facts and Episodes with their vectors and embedder identity in one SQLite file (or `:memory:`). Search is exact cosine similarity computed in Python over the user's matching rows. Every blocking sqlite call runs in a worker thread.
- `FileSkillStore`: one JSON file per skill in a directory, with checks that a name can never address a path outside it.

## User Stories

1. As a use-case author, I want `upsert` to store entries and replace one with the same user and id, atomically per call.
2. As a use-case author, I want `get` to return the entry for one user or `None`.
3. As a use-case author, I want `search` to return at most `limit` hits for one user, best first, ties broken by id, with cosine scores.
4. As a use-case author, I want search to skip entries made by a different embedder identity, and to reject a query whose length differs from `embedder.dimensions`.
5. As a use-case author, I want filters on kind, active facts only and episode status, applied to both `search` and `list`.
6. As a use-case author, I want `list` ordered by creation time then id.
7. As a use-case author, I want `delete` and `delete_user` to be idempotent and never touch another user's entries.
8. As an operator, I want `count_stale` to count entries across all users whose embedder identity differs from the given one.
9. As an adapter user, I want a blank user id or `limit < 1` rejected with `PermanentAdapterError`.
10. As an operator, I want data to persist in a file and be reopened by a new instance.
11. As an architect, I want `sqlite3` calls never to block the event loop (run in a worker thread, serialized by a lock).
12. As a maintainer, I want sqlite failures raised as `TransientAdapterError` (locked or busy) or `PermanentAdapterError`, never as `sqlite3` exceptions, with no entry text in error messages.
13. As a use-case author, I want facts and episodes round-trip without loss (timestamps, `superseded_by`, status, profile key).
14. As a use-case author, I want a `FileSkillStore` that saves, gets, lists (ordered by name) and deletes skills, where save replaces and a missing name gives `None` or a silent delete.
15. As a security reviewer, I want names with a path separator, `..`, an absolute path, NUL or blank text rejected with `PermanentAdapterError` on every method.
16. As a security reviewer, I want a name that would resolve outside the store directory (for example through a symlink) rejected.
17. As an operator, I want skill writes to be atomic, so a crash never leaves a half-written file.
18. As an operator, I want a corrupt skill file reported as `PermanentAdapterError` naming the skill, not its content.
19. As a maintainer, I want both adapters to satisfy their Protocols structurally, checked by mypy.

## Implementation Decisions

- Modules: `memory/adapters/sqlite_index.py`, `memory/adapters/file_skill_store.py`. Not re-exported from `june.memory`.
- Schema: table `entries(user_id, id, kind, created_at, superseded_by, status, item_json, vector_json, embedder_name, embedder_version, embedder_dimensions)` with primary key `(user_id, id)` and an index on `(user_id, kind)`. Vectors and items are stored as JSON text; `created_at` as an ISO-8601 UTC string, which sorts correctly.
- One connection opened with `check_same_thread=False`, guarded by a `threading.Lock`; each port method runs its work through `asyncio.to_thread`. A `close()` method releases the connection.
- Search is brute force: select rows for the user with the embedder identity and filters, score in Python, sort by `(-score, id)`, slice. Adequate for personal-scale memory; revisit with ADR if it is not.
- Cosine of a zero vector is 0.0.
- Skill file name is `<name>.json` in the root directory; the root is created on first use. Name validation: non-blank, no `/`, no `\`, no NUL, not `.` or `..`, not containing `..` as a path part, not absolute. Final check: the resolved file's parent equals the resolved root.
- Errors reuse `TransientAdapterError` and `PermanentAdapterError`; sqlite `OperationalError` with "locked" or "busy" is transient, all other `sqlite3.Error` and `OSError` are permanent (`OSError` on write is permanent too).
- No settings or composition wiring (P2.7).

## Testing Decisions

- Public adapter classes only, real SQLite (`:memory:` and `tmp_path` files) and real files; no mocking of sqlite.
- Cover every story above, including persistence across instances, cross-user isolation, stale count, embedder mismatch and filters, event-loop responsiveness while a call runs, path-escape names and symlink escape.
- `make check` passes; coverage of both modules at least 80%.

## Out of Scope

- Approximate nearest neighbour indexes and sqlite extensions.
- Migrations beyond creating the table; schema version table.
- Settings keys, composition wiring and the shared contract suite (P2.7).

## Further Notes

- Linear: SHIP-321.
