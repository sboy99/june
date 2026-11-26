# Memory ports (SHIP-319, P2.2)

Status: ready-for-agent
Source: Linear SHIP-319, milestone "Phase 2: Memory"
Branch: `contactsagarbera/ship-319-p22-memory-ports` (stacked on SHIP-318)

## Problem Statement

`june.memory.ports` holds four empty Protocol stubs: `VectorIndex`, `Embedder`, `SkillStore`, `Summarizer`. The embedder and index adapters (P2.3, P2.4), the remember/recall/forget and consolidation use cases (P2.5, P2.6) and the contract suites (P2.7) cannot be built against them. There is no shared shape for vectors, index entries, search hits or summarizer output, and no statement of what an adapter must do or which errors may escape.

## Solution

`june.memory.ports` defines small immutable port-level value types and four async Protocols, each with a written contract in its docstring, in the same style as `ChatModel`. The contracts are precise enough that the P2.7 contract suites can be written from them alone. Ports speak only memory domain types and memory port types: no vendor, `llm` or `runtime` types, because same-level modules cannot import each other.

## User Stories

1. As an adapter author, I want an `Embedder` that turns a batch of texts into vectors, so that one call serves many memories.
2. As an adapter author, I want an `Embedder` to expose a name, a version and a fixed dimension count, so that stored vectors can be tied to the model that made them.
3. As a use-case author, I want an embedder identity value (name, version, dimensions), so that I can compare it with what the index holds.
4. As an adapter author, I want the embedder contract to say it returns one vector per input text, in input order, each with exactly `dimensions` finite floats, so that callers can zip results with inputs.
5. As an adapter author, I want an empty input batch to return an empty result without calling the vendor, so that callers need no special case.
6. As an adapter author, I want the contract to say the same text gives the same vector for the same name and version, so that an offline hashing embedder is testable.
7. As an adapter author, I want transient embedder failures to be retried internally and then raised as `TransientAdapterError`, and permanent ones as `PermanentAdapterError`, so that callers know what to retry.
8. As a use-case author, I want a `VectorIndex` that stores entries (a Fact or Episode with its vector and embedder identity) and finds the nearest ones for one user, so that recall is similarity search.
9. As a use-case author, I want upsert by entry id to replace an existing entry, so that marking a fact superseded or an episode consolidated is a re-upsert.
10. As a use-case author, I want search to take the query vector, the user id, a limit and optional filters (kind, active facts only, pending episodes only), so that recall and consolidation use the same port.
11. As a use-case author, I want search results as hits carrying the entry and a similarity score (higher is closer, cosine in [-1, 1]), ordered best first, so that ranking can combine similarity with recency decay.
12. As a use-case author, I want search to never return another user's entries, so that users are isolated at the port.
13. As a use-case author, I want search to skip entries made by a different embedder identity and a query whose dimension does not match to be rejected with `PermanentAdapterError`, so that vectors from two models are never compared.
14. As an operator, I want to ask the index how many entries were made by an embedder identity other than the current one, so that a model change is detectable and re-embedding can be planned.
15. As a use-case author, I want to list a user's entries by kind and episode status without a query vector, so that consolidation can find pending episodes.
16. As a use-case author, I want to fetch one entry by id for one user, getting none when it does not exist, so that dedupe and supersede can read existing facts.
17. As a use-case author, I want to list a user's active facts for supersede and dedupe, so that those domain rules receive the existing facts.
18. As a use-case author, I want to delete entries by id and to delete everything for a user, so that forget works by id or by user.
19. As a use-case author, I want deleting a missing id to succeed silently, so that forget is idempotent.
20. As an adapter author, I want a `limit` below 1 or an empty user id rejected with `PermanentAdapterError`, so that bad calls fail the same way everywhere.
21. As a use-case author, I want a `SkillStore` to save, get, list and delete skills by name, so that learned procedures persist.
22. As a use-case author, I want save to replace a skill with the same name, so that name stays the identity.
23. As a use-case author, I want get of a missing skill to return none and delete of a missing skill to succeed, so that callers need no exceptions for absence.
24. As a security reviewer, I want the contract to require that a name that could escape the store (path separators, `..`, absolute paths, NUL) is rejected with `PermanentAdapterError` on every operation, so that a file-based store cannot be tricked.
25. As a use-case author, I want listing skills to return them ordered by name, so that output is stable.
26. As a use-case author, I want a `Summarizer` that turns a conversation transcript into one episode summary, so that remember-episode has text to store.
27. As a use-case author, I want a `Summarizer` that distills pending episodes into candidate facts (text and optional profile key), so that consolidation can supersede and dedupe them with the domain rules.
28. As an architect, I want transcripts and fact candidates defined as memory port types (`TranscriptTurn`, `FactCandidate`), so that `memory` does not import `llm` and the composition root can fill the port with an `llm`-backed adapter.
29. As an adapter author, I want the summarizer contract to say blank candidate text is never returned, and an empty transcript or empty episode batch returns an empty or rejected result as specified, so that outputs are always valid.
30. As an adapter author, I want every port to say that only `TransientAdapterError` and `PermanentAdapterError` may escape and that error text never contains secrets or API keys, so that failures are uniform.
31. As a test author, I want any class with the right methods to satisfy each port structurally, so that fakes need no inheritance.
32. As an architect, I want `memory.ports` to import only the standard library, `june.shared` and `june.memory.domain`, so that all five import contracts keep passing.
33. As a maintainer, I want the port types and Protocols exported from `june.memory`, so that other modules use one import path.
34. As a maintainer, I want new terms in the glossary, so that code and docs use the same words.

## Implementation Decisions

- **Style**: standard-library frozen dataclasses (slots allowed) and `typing.Protocol`, in `june/memory/ports.py`, re-exported from `june.memory` with an accurate `__all__`. All port methods are `async`. No pydantic. Invalid port-level values raise `DomainError`, as the domain types do.
- **Vector**: `tuple[float, ...]`. Immutable, hashable, no numpy dependency. Values must be finite.
- **`EmbedderInfo`**: `name`, `version`, `dimensions` (positive int). Equality is by value; it is the "embedder identity" stored with every entry.
- **`Embedder`**: `info` property returning `EmbedderInfo`; `embed(texts: Sequence[str]) -> list[Vector]`. Contract in the docstring: one vector per text in order, length `info.dimensions`, deterministic for a given name and version, empty batch returns an empty list, blank text is allowed (callers filter), retry transient failures internally up to the configured count then raise, only the two adapter errors escape.
- **`IndexEntry`**: `item` (a `Fact` or `Episode`), `vector`, `embedder` (`EmbedderInfo`); derived `id`, `user_id` and `kind` (`fact` or `episode`) come from the item. Validation: vector length equals `embedder.dimensions`. The index is the only store of Facts and Episodes in Phase 2 (there is no separate fact store port), so an entry carries the full domain item including `superseded_by` and episode status.
- **`SearchFilter`**: optional `kind`; `active_only` (facts that are not superseded; episodes unaffected); `episode_status` (optional). Defaults match everything.
- **`SearchHit`**: `entry`, `score`. Score is cosine similarity; adapters that use another metric must map it to this meaning.
- **`VectorIndex`** methods: `upsert(entries)`, `get(user_id, entry_id) -> IndexEntry | None`, `search(user_id, vector, *, limit, filter, embedder) -> list[SearchHit]`, `list(user_id, filter) -> list[IndexEntry]` (ordered by creation time, then id), `delete(user_id, ids)`, `delete_user(user_id)`, `count_stale(embedder) -> int`. Contract: user isolation on every method; upsert replaces by id and is atomic per call; `search` considers only entries whose embedder identity equals the `embedder` argument and raises `PermanentAdapterError` when the query dimension differs from it; results best first, ties broken by id; `limit >= 1`; deletes are idempotent; `count_stale` counts entries across all users whose embedder identity differs; only the two adapter errors escape; blocking vendor calls must not block the event loop (adapter concern, stated in the docstring).
- **`SkillStore`** methods: `save(skill)`, `get(name) -> Skill | None`, `list() -> list[Skill]` (ordered by name), `delete(name)`. Contract: save replaces by name; get and delete of a missing name are not errors; a name containing a path separator, `..`, an absolute path or a NUL is rejected with `PermanentAdapterError` on every method; only the two adapter errors escape.
- **`Summarizer`** methods: `summarize(turns: Sequence[TranscriptTurn]) -> str` and `distill(episodes: Sequence[Episode]) -> list[FactCandidate]`. `TranscriptTurn` has `role` (`user` or `assistant` only; tool activity is not representable, which supports the SHIP-323 rule) and non-blank `content`. `FactCandidate` has non-blank `text` and optional `profile_key`. Contract: `summarize` of an empty sequence raises `PermanentAdapterError`; the result is non-blank; `distill` of an empty sequence returns an empty list without calling the vendor; candidates have non-blank text; the summarizer neither stores nor deduplicates (domain rules do); only the two adapter errors escape; error text never contains transcript content.
- **Secrets filtering** is not a port concern; the consolidation use case owns it (SHIP-323).
- **Errors**: reuse `TransientAdapterError` and `PermanentAdapterError` from `june.shared`; no new error types.
- **Layering**: `memory.ports` imports the standard library, `june.shared` and `june.memory.domain`. No `.importlinter` change. Verify with `make arch`.
- **Stubs replaced**: the four existing stub docstrings are removed.
- **Glossary**: add Embedder identity, Index entry, Search hit, Fact candidate, Transcript turn (owner: memory); the existing port terms stay. No ADR: the decisions follow ADR 0002 and ADR 0004; the index holding domain items is recorded here and may be revisited when P2.4 lands.

## Testing Decisions

- A good test uses only the public `june.memory` API: it constructs values, runs a minimal fake against the Protocol and asserts behaviour. It does not inspect private attributes.
- Single seam: unit tests of `june.memory.ports` and its re-exports. The port contracts themselves are executed against real adapters in P2.7; this ticket only proves the types and that a fake satisfies each Protocol.
- Cover: construction and validation of `EmbedderInfo`, `IndexEntry` (dimension mismatch, non-finite values), `SearchFilter`, `SearchHit`, `TranscriptTurn` (role limited to user and assistant, blank content) and `FactCandidate`; immutability and hashability; a fake class per Protocol with no inheritance assigned to a Protocol-typed variable (checked by mypy in `make check`) and called at runtime; exports from `june.memory`.
- Prior art: `tests/unit/test_llm_ports.py`, `tests/unit/test_memory_domain_types.py`.
- Architecture contracts keep passing (`make arch`).
- Done when: `make check` passes, coverage of `june.memory.ports` is at least 80%, and each port's contract is written in its Protocol docstring.

## Out of Scope

- Any adapter: hashing and API embedders (P2.3), SQLite index and file skill store (P2.4), the `llm`-backed summarizer (wired in P2.7).
- Remember, recall, forget and consolidation use cases (P2.5, P2.6), including similarity and recency ranking, secret filtering and locking.
- Contract suites run against adapters and the `composition.py` wiring (P2.7).
- Skill extraction by the summarizer (no skill candidates in Phase 2).
- Settings for embedder or index choice.

## Further Notes

- Linear: SHIP-319, project June, milestone "Phase 2: Memory".
- Seam check: one seam (public `june.memory` API), matching the earlier Phase 2 and Phase 1 specs. Proceeding without a separate confirmation, as for SHIP-318; say so if you want a different seam.
- Open decision for review: the index holds full Facts and Episodes (story 8). The alternative is a separate fact/episode store port next to a thinner index; it was rejected because the ticket lists exactly four ports and two stores would duplicate user isolation and deletion.
