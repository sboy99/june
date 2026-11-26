# End-of-session consolidation trigger (SHIP-329, P3.5)

Status: ready-for-agent
Source: Linear SHIP-329, milestone "Phase 3: Conversation and runtime"
Branch: `contactsagarbera/ship-329-p35-end-of-session-consolidation` (stacked on SHIP-328)

## Problem Statement

Memory has use cases to summarise a conversation into an Episode and to Consolidate Episodes into Facts, but nothing calls them. Calling them inline would make the user wait for model calls after the reply is already written.

## Solution

`june.runtime` gains a `SessionCloser`. When a Session ends, the caller hands it the Session and gets control back at once. In the background it stores the Session's transcript as a pending Episode and, every N ended sessions for that user, runs Consolidation. Background failures are logged, never raised into the reply path.

## User Stories

1. As the runtime, I want `end_session(session)` to return immediately, so the user's reply is never delayed by memory work.
2. As the runtime, I want the Session's Turns stored as one pending Episode for the Session's user, in turn order (user then assistant text).
3. As the runtime, I want a Session with no Turns to do nothing and not count toward the trigger.
4. As the runtime, I want Consolidation run for a user after every N-th ended Session of that user.
5. As the runtime, I want the count kept per user, so one user's sessions never trigger another's Consolidation.
6. As the runtime, I want the Episode stored before Consolidation runs, so the newest Session is included.
7. As the runtime, I want a failure to store the Episode logged and not counted, and Consolidation then not run for it.
8. As the runtime, I want a failed Consolidation logged, and the next ended Session to count and trigger normally.
9. As the runtime, I want an unexpected exception in the background work logged with its trace, never lost silently and never raised to the caller of `end_session`.
10. As the runtime, I want `drain()` to wait for all background work to finish, so shutdown and tests lose nothing.
11. As the runtime, I want N below 1 rejected with `DomainError`.
12. As a maintainer, I want new terms in the glossary.

## Implementation Decisions

- `SessionCloser(remember_conversation, consolidate, every_n_sessions=3)`; `end_session(session)` is synchronous and schedules an `asyncio` task on the running loop; `drain()` is async.
- Depends on two small runtime-owned protocols that match `RememberConversation.execute(user_id, turns)` and `Consolidate.execute(user_id)`, so the runtime tests need no database.
- Tasks are held in a set until done so they are not garbage collected; per-user work is chained so a user's sessions are processed in the order they ended (one background worker per `end_session` call, serialized by a per-user lock).
- The ended-session count is in memory and starts at zero on each process start. Persisting it is out of scope.
- Only `AgentError` is expected from the use cases and is logged as a warning with its code; any other exception is logged with `exception`. `CancelledError` propagates.
- Not wired into `build_app` yet: no Summarizer adapter exists. SHIP-330 wires it with what exists.

## Testing Decisions

- Through the public API: fake `remember_conversation` and `consolidate` recorders; assert on what they were called with and in what order, after `drain()`. A blocking fake proves `end_session` returns before the work finishes.
- Cover every story above. Prior art: `tests/unit/test_runtime_loop.py`.
- `make check` passes; `june.runtime` coverage at least 80%.

## Out of Scope

- A time-based or idle-based session end, persisting the count, a Summarizer adapter, retrying failed background work, scheduling through `june.scheduling`.

## Further Notes

- Linear: SHIP-329.
