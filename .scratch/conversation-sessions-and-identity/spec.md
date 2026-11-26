# Conversation sessions and identity (SHIP-325, P3.1)

Status: ready-for-agent
Source: Linear SHIP-325, milestone "Phase 3: Conversation and runtime"
Branch: `contactsagarbera/ship-325-p31-conversation-sessions-and` (from main; first of the Phase 3 stack)

## Problem Statement

The agent has no notion of a conversation. Nothing records which user is talking, which Session a message belongs to, or what was said earlier, so the runtime cannot build history or hand turns to memory.

## Solution

`june.conversation` gains the Session and Turn value types, a `SessionStore` port with a contract suite, and two adapters (in-memory and SQLite). The composition root wires the SQLite store.

## User Stories

1. As the runtime, I want a `Session` with an id, a `user_id`, a creation time and an ordered tuple of turns, so I know who is talking and what was said.
2. As the runtime, I want a `Turn` (user message, agent reply, creation time) as an immutable value.
3. As the runtime, I want `Session.start(user_id, session_id, now)` to give an empty session.
4. As the runtime, I want `session.with_turn(turn)` to return a new Session and leave the original untouched.
5. As the runtime, I want blank ids, blank messages, and non-UTC times rejected with `DomainError`.
6. As the runtime, I want `SessionStore.save(session)` to create or replace a session, turns included.
7. As the runtime, I want `get(session_id)` to return the session or `None`.
8. As the runtime, I want `list_for_user(user_id)` to return only that user's sessions, oldest first.
9. As the runtime, I want `delete(session_id)` to remove a session and its turns; deleting a missing session is not an error.
10. As the runtime, I want turn order preserved exactly through save and get.
11. As an operator, I want sessions to survive a restart, so the SQLite store keeps them in a file.
12. As an operator, I want a corrupt stored row reported as `PermanentAdapterError`, and a busy database as `TransientAdapterError`; vendor exceptions never escape and messages carry no secrets.
13. As a maintainer, I want one contract suite run against both adapters.
14. As an architect, I want `sqlite3` only in the adapter and all five import contracts passing.
15. As a maintainer, I want `build_app` to expose a `session_store`, and new terms in the glossary.

## Implementation Decisions

- Domain types are plain frozen dataclasses in the conversation module (ADR 0002: domain layer only in `memory/`). `Session.turns` is a tuple; `with_turn` returns a copy.
- A `Turn` is one user message plus the agent's complete reply (glossary). In-flight turns are not stored.
- `SessionStore` methods are async: `save`, `get`, `list_for_user`, `delete`. Only `TransientAdapterError` and `PermanentAdapterError` escape.
- A blank id passed to a store raises `PermanentAdapterError`, like the memory adapters.
- SQLite adapter mirrors `SqliteVectorIndex`: one connection, a lock, work in a worker thread. Two tables, `sessions` and `turns` (position-ordered); `save` rewrites a session's turns in one transaction.
- The in-memory adapter keeps immutable `Session` values in a dict; it is for tests and offline runs.
- Composition: `App.session_store` is a `SqliteSessionStore` at `data_dir/sessions.db`.
- Converting turns to `Message`s or `TranscriptTurn`s is the runtime's job (conversation cannot import llm or memory).
- No ADR: follows ADR 0001, 0002 and 0004.

## Testing Decisions

- Test external behaviour through `june.conversation` and the contract suite. No assertions on SQL or internals.
- Contract suite parametrized over both adapters; SQLite also tested for persistence across reopen and corrupt rows.
- Prior art: `tests/contract/test_skill_store_contract.py`, `tests/unit/test_memory_sqlite_index.py`.
- `make check` passes; coverage of `june.conversation` at least 80%.

## Out of Scope

- Context building, the agent loop, memory hand-off, session expiry or pagination, a CLI chat command.
