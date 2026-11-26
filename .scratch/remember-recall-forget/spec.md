# Remember, recall and forget use cases (SHIP-322, P2.5)

Status: ready-for-agent
Source: Linear SHIP-322, milestone "Phase 2: Memory"
Branch: `contactsagarbera/ship-322-p25-remember-recall-and-forget-use` (stacked on SHIP-321)

## Problem Statement

The memory ports, domain rules and adapters exist, but nothing orchestrates them. The runtime cannot store a fact or an episode, ask what is relevant to a query, or delete a user's memories.

## Solution

Four small async use cases in `june.memory.application`, built only on the ports, the domain rules and `june.shared` (`Clock`, `IdGenerator`):

- `RememberFact`: store a fact, deduplicating and superseding with the domain rules.
- `RememberEpisode`: store a pending episode summary.
- `Recall`: embed a query, search the index, and rank by similarity times recency decay.
- `Forget`: delete by id or all memories of a user.

## User Stories

1. As the runtime, I want to remember a fact for a user with a source and optional profile key, getting the stored `Fact` back.
2. As the runtime, I want remembering the same text again (after normalization) to return the existing active fact and write nothing, so that memory has no duplicates.
3. As the runtime, I want a new fact with a profile key to supersede the user's active facts with the same key, marking each as superseded by the new fact, in one atomic index write.
4. As the runtime, I want superseded facts to keep their original vectors, so that no re-embedding is needed.
5. As the runtime, I want to remember an episode summary for a user, stored as a pending `Episode`.
6. As the runtime, I want blank text, summary, user id or source rejected with `DomainError` before any embedder or index call.
7. As the runtime, I want ids and timestamps to come from the injected `IdGenerator` and `Clock`, so that tests are deterministic.
8. As the runtime, I want `Recall` to embed the query and return the best `limit` memories for one user, never another user's.
9. As the runtime, I want recall to exclude superseded facts.
10. As the runtime, I want each recalled memory to carry the item, its cosine similarity, its recency decay and the final score (similarity times decay), best first, ties broken by id.
11. As the runtime, I want a newer memory to beat an older one of equal similarity, so that recency matters.
12. As the runtime, I want recall to drop memories whose similarity is not above a minimum (default 0), so that unrelated memories are not returned.
13. As the runtime, I want to restrict recall to facts or episodes.
14. As the runtime, I want recall to fetch more candidates than `limit` before re-ranking, so that recency can lift a slightly less similar but newer memory.
15. As the runtime, I want a `limit` below 1 or a blank query rejected with `DomainError`.
16. As the runtime, I want `Forget` to delete given ids for one user, idempotently, and to delete everything for a user.
17. As the runtime, I want forgetting to never touch another user's entries.
18. As the runtime, I want adapter errors (`TransientAdapterError`, `PermanentAdapterError`) to pass through unchanged.
19. As an architect, I want `memory.application` to import only the standard library, `june.shared`, `june.memory.domain` and `june.memory.ports`, so that all five import contracts keep passing.
20. As a maintainer, I want the use cases and `RecalledMemory` exported from `june.memory`, and new terms in the glossary.

## Implementation Decisions

- One module per use case under `memory/application/`: `remember.py` (both remember classes), `recall.py`, `forget.py`. Plain classes with constructor injection and one `execute` method each. All `async`.
- `RememberFact(index, embedder, clock, ids)`. `execute(user_id, text, source, profile_key=None) -> Fact`. Steps: build the `Fact` (validates); list the user's active facts with `SearchFilter(kind="fact", active_only=True)`; if `find_duplicate` finds one, return it; embed the text; compute `supersede(existing, fact)`; upsert the new entry plus the superseded entries (each reusing its stored vector and embedder identity) in one call.
- `RememberEpisode(index, embedder, clock, ids)`. `execute(user_id, summary) -> Episode`.
- `Recall(index, embedder, clock, half_life=DEFAULT_HALF_LIFE, candidate_multiplier=4)`. `execute(user_id, query, *, limit=5, kind=None, min_similarity=0.0) -> list[RecalledMemory]`. Candidates come from `index.search(..., limit=limit * candidate_multiplier, filter=SearchFilter(kind=kind, active_only=True), embedder=embedder.info)`. Hits with similarity at or below `min_similarity` are dropped; the rest are sorted by `(-score, id)` and cut to `limit`.
- `RecalledMemory(item, similarity, recency, score)` is a frozen dataclass.
- `Forget(index)`. `by_ids(user_id, ids)`, `everything(user_id)`.
- Secret filtering and consolidation are SHIP-323, not here.
- No ADR: the decisions follow ADR 0002 and 0004. Glossary: add Recalled memory.

## Testing Decisions

- Public API only (`june.memory`), real collaborators: `HashingEmbedder`, `SqliteVectorIndex(":memory:")`, `FixedClock`, a counting `IdGenerator` fake. No mocking of ports except a failing fake for error pass-through and an embedder spy to prove no call is made on invalid input.
- Cover every story above. `make check` passes; coverage of `june.memory.application` at least 80%.

## Out of Scope

- Consolidation, secret filtering, locking (P2.6), settings and composition wiring (P2.7), summarizer-driven remember, retention purging.

## Further Notes

- Linear: SHIP-322.
