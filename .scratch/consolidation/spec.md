# Consolidation use case (SHIP-323, P2.6)

Status: ready-for-agent
Source: Linear SHIP-323, milestone "Phase 2: Memory"
Branch: `contactsagarbera/ship-323-p26-consolidation-use-case` (stacked on SHIP-322)

## Problem Statement

Episodes pile up as `pending` and never become durable facts. Nothing calls the `Summarizer` port, so a conversation cannot be turned into an episode, and pending episodes cannot be distilled into facts.

## Solution

Two small async use cases in `june.memory.application`, built only on ports, domain rules, `june.shared` and the existing remember use cases:

- `RememberConversation`: summarize transcript turns and store the result as a pending episode.
- `Consolidate`: distill a user's pending episodes into facts through the summarizer, then mark those episodes consolidated. Idempotent, locked per user, and safe to fail.

## User Stories

1. As the runtime, I want `RememberConversation` to turn transcript turns into one pending episode via `Summarizer.summarize`, returning the `Episode`.
2. As the runtime, I want an empty list of turns rejected with `DomainError` before any summarizer, embedder or index call.
3. As the runtime, I want tool activity never to reach the summarizer. `TranscriptTurn` cannot represent it, so the use case accepts only `TranscriptTurn` values.
4. As the runtime, I want `Consolidate.execute(user_id)` to load the user's pending episodes, ask the summarizer to distill them, and store each candidate through `RememberFact` (so dedupe and supersede apply), with source `consolidation`.
5. As the runtime, I want episodes marked `consolidated` only after every fact is stored, keeping their original vectors, in one atomic index write.
6. As the runtime, I want consolidation to be idempotent: running again with no pending episodes returns an empty result and calls neither summarizer nor embedder.
7. As the runtime, I want a summarizer failure (`TransientAdapterError`, `PermanentAdapterError`) to pass through unchanged and leave every episode pending and no fact stored.
8. As the runtime, I want a failure while storing facts to leave episodes pending; a rerun does not duplicate facts that were already stored (dedupe).
9. As the runtime, I want candidates that contain secrets (API keys, bearer tokens, `password=...`) dropped and never stored as facts, using the existing redaction patterns in `june.observability`.
10. As the runtime, I want the result to say how many episodes were consolidated, how many facts were stored, and how many candidates were skipped (secret or duplicate).
11. As the runtime, I want concurrent consolidations for the same user serialized by a lock, so the second sees nothing pending and does nothing; different users do not block each other.
12. As the runtime, I want a blank user id rejected with `DomainError`.
13. As an architect, I want `memory.application` to import only the standard library, `june.shared`, `june.observability`, `june.memory.domain` and `june.memory.ports`, so all five import contracts keep passing.
14. As a maintainer, I want both use cases and `ConsolidationResult` exported from `june.memory`, and new terms in the glossary.

## Implementation Decisions

- New module `memory/application/consolidate.py` with `ConsolidationResult`, `RememberConversation`, `Consolidate`. Plain classes, constructor injection, one `execute` method each, all `async`.
- `RememberConversation(summarizer, remember_episode)`. `execute(user_id, turns) -> Episode`: validate, `summarizer.summarize(turns)`, then `RememberEpisode.execute`.
- `Consolidate(index, summarizer, remember_fact)`. Steps under the user's lock: list entries with `SearchFilter(kind="episode", episode_status=PENDING)`; if none, return the empty result; `distill`; drop secret candidates; `remember_fact.execute(user_id, text, "consolidation", profile_key)` for each; upsert the episode entries with `mark_consolidated()`.
- Secret test: a candidate is secret when `redact_text(text) != text`. One source of truth for patterns, no duplicate regex. Allowed by the layer contract (`observability` sits below `memory`).
- Counting: list the user's active facts once before storing; a fact counts as stored when the id returned by `RememberFact` was not among them and is new within the run, otherwise it counts as skipped (duplicate).
- Lock: `dict[str, asyncio.Lock]` keyed by user id, held on the instance. In-process only; documented as such. Multi-process locking is out of scope.
- No ADR: follows ADR 0002 and 0004. Glossary: add Consolidation result.

## Testing Decisions

- Public API only (`june.memory`), real collaborators: `HashingEmbedder`, `SqliteVectorIndex(":memory:")`, `FixedClock`, counting ids, and a scripted fake `Summarizer` (failing, secret-producing, call-counting).
- Cover every story above. `make check` passes; coverage of `june.memory.application` at least 80%.

## Out of Scope

- Skill extraction, retention purging, scheduling consolidation, settings and wiring (P2.7), a real LLM summarizer adapter.

## Further Notes

- Linear: SHIP-323.
