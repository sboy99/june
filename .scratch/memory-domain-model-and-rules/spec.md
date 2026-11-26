# Spec: Memory domain model and rules (SHIP-318, P2.1)

Status: ready-for-agent
Source: Linear SHIP-318, milestone "Phase 2: Memory"
Branch: `contactsagarbera/ship-318-p21-memory-domain-model-and-rules` (stacked on `main`; first of the Phase 2 stack SHIP-318 to SHIP-324)

## Problem Statement

june must remember things about the user and about what happened, but the rules for what to keep, merge, rank and forget do not exist yet. `june.memory.domain` is an empty package. If those rules are written first inside adapters or use cases (SQLite queries, the summarizer), they become untestable without I/O and drift between implementations. Later Phase 2 tickets (ports, embedders, index, use cases, consolidation) all need one shared, pure vocabulary and one set of rules.

## Solution

`june.memory.domain` provides the immutable value types **Fact**, **Episode** and **Skill**, and pure functions that implement the memory rules: superseding a profile fact, deduplicating facts, recency decay for ranking, and retention. Nothing in the package does I/O, reads the clock, generates ids or uses async. Time is always passed in. Domain tests run with no fixtures.

## User Stories

1. As a memory author, I want an immutable `Fact`, so that a stored statement cannot be mutated by accident.
2. As a memory author, I want a `Fact` to carry id, owner user id, text, optional profile key, source, creation time and a supersession marker, so that the rules have what they need.
3. As a memory author, I want an immutable `Episode` with id, user id, summary, creation time and a consolidation status (pending or consolidated), so that consolidation can find pending work.
4. As a memory author, I want an immutable `Skill` with name, description, steps and creation time, so that a learned procedure is a value like the others.
4a. As a memory author, I want construction to reject blank text, a blank skill name, naive datetimes and an empty user id, so that invalid memory cannot exist.
5. As a memory author, I want the types to be hashable and equal by value, so that tests and sets behave predictably.
6. As a memory author, I want "change" operations (mark consolidated, mark superseded) to return a new object, so that nothing is mutated in place.
7. As the agent, I want a new fact with a profile key (for example `name` or `timezone`) to supersede the user's current fact with the same key, so that I never hold two contradicting values.
8. As the agent, I want superseding to keep the old fact, marked as superseded by the new one, so that history is not lost.
9. As the agent, I want profile keys compared case-insensitively and trimmed, so that "Timezone" and "timezone " are the same key.
10. As the agent, I want facts without a profile key never to supersede anything, so that free-form facts accumulate.
11. As the agent, I want supersede to apply only within one user, so that one user's facts never affect another's.
12. As the agent, I want a new fact whose normalized text equals an existing active fact of the same user to be recognised as a duplicate, so that memory does not fill with repeats.
13. As the agent, I want duplicate detection to ignore case, surrounding whitespace and repeated inner whitespace, so that trivial variations still match.
14. As the agent, I want superseded facts ignored by duplicate checks, so that an old value can be stated again later.
15. As the agent, I want a recency decay factor between 0 and 1 for a memory's age, so that recall can combine similarity with how recent something is.
16. As the agent, I want decay to be 1.0 at age zero and to fall monotonically with age, so that newer memories rank higher.
17. As the agent, I want decay to follow a half-life, so that the behaviour is easy to reason about and tune.
18. As the agent, I want a future-dated memory (clock skew) to count as age zero, so that decay never exceeds 1.
19. As an operator, I want a retention rule that says whether an episode is expired given its age and a retention period, so that old episodes can be forgotten.
20. As an operator, I want pending episodes never to expire, so that unconsolidated information is not lost.
21. As an operator, I want facts to be exempt from time-based expiry, so that durable knowledge persists until deleted or superseded.
22. As an operator, I want superseded facts to be eligible for retention purge after a grace period, so that history does not grow forever.
23. As a developer, I want all rules to be pure functions of their arguments (including `now`), so that tests need no fixtures or fake clocks.
24. As an architect, I want the domain package to import no pydantic, sqlite3, httpx, anthropic, openai, asyncio or adapters, so that the `Pure domain` contract keeps passing.
25. As a developer, I want the types and rules importable from `june.memory.domain`, so that application code does not reach into submodules.
26. As a maintainer, I want new terms in the glossary, so that code and docs use the same words.

## Implementation Decisions

- **Types**: frozen dataclasses (slots allowed). Validation in `__post_init__` raises `DomainError` from `june.shared` (shared is a lower layer; allowed). Datetimes must be timezone-aware UTC.
- **Fact**: id, user_id, text, profile_key (optional), source (free label, for example `user` or `consolidation`), created_at, superseded_by (optional fact id). "Active" means `superseded_by is None`.
- **Episode**: id, user_id, summary, created_at, status (`pending` or `consolidated`; a small enum). Transition helper returns a new Episode.
- **Skill**: name, description, ordered steps (tuple of strings), created_at. Name is the identity.
- **Supersede rule**: given the user's existing facts and a new fact, return the existing facts to supersede (same user, same normalized profile key, active) and the replaced copies marked with the new fact's id. The rule does not decide persistence.
- **Dedupe rule**: given existing facts and a candidate, report the existing active fact with the same user and normalized text, or none. Normalization: trim, collapse inner whitespace, casefold.
- **Recency decay**: exponential half-life, `0.5 ** (age / half_life)`, age clamped at zero. Half-life is an explicit argument with a named default constant. Returns float in (0, 1].
- **Retention**: pure predicates taking `now` and policy values (episode retention period, superseded-fact grace period). Defaults live as named constants. Pending episodes and active facts never expire.
- **Policy values** are plain arguments or a small frozen `RetentionPolicy` dataclass; no config reading (`config.py` is the only reader of environment variables, and wiring is Phase 2 P2.7).
- **No I/O, no async, no clock, no id generation** in the package. Callers pass `now` and ids.
- **Public surface**: re-export from `june.memory.domain` with an accurate `__all__`. `june.memory.__init__` is unchanged (ports are P2.2).
- **Layering**: no `.importlinter` changes. Domain imports only the standard library and `june.shared`.
- **Glossary**: add Profile key, Supersede, Active fact, Recency decay, Retention (owner: memory) in the same change. The existing Episode, Fact, Skill entries stay.
- **ADR**: none; consistent with ADR 0002 (domain layer in memory) and ADR 0004 (sync domain).

## Testing Decisions

- A good test calls the public `june.memory.domain` API and asserts returned values and raised errors. It does not inspect private attributes or module layout.
- Single seam: unit tests of `june.memory.domain` with plain constructed values, no fixtures (the "done when" of the ticket). Datetimes are literals.
- Cover: construction validation (blank text, naive datetime, bad status); immutability (assignment raises, transitions return new objects); supersede (match, case and whitespace, no key, other user, already superseded, history kept); dedupe (normalization, other user, superseded ignored); decay (1.0 at zero, half at one half-life, monotonic, future clamped); retention (episode expiry boundary, pending never expires, active facts never expire, superseded after grace).
- The existing `tests/contract/test_architecture.py` / `make arch` stays the check for the Pure domain contract.
- Prior art: `tests/unit/test_shared_errors.py` and `tests/unit/test_shared_clock.py` (behavioural, Arrange-Act-Assert, descriptive names). New file names `tests/unit/test_memory_domain_*.py`.
- Done when: `make check` passes, coverage on `june.memory.domain` is at least 80%, and tests run with no fixtures.

## Out of Scope

- Ports, embedders, vector index, skill store, summarizer (P2.2 to P2.4).
- Remember, recall, forget and consolidation use cases (P2.5, P2.6); secret filtering belongs there.
- Persistence, similarity scoring, ranking combination of similarity and decay (application layer).
- Reading retention or half-life from settings; wiring in `composition.py`.

## Further Notes

- Linear: SHIP-318, project June, milestone "Phase 2: Memory". Done when: domain tests run with no fixtures.
- Seam check: one seam (public domain API), matching the prior Phase 1 specs. Proceeding without a separate confirmation because the whole flow was requested to run unattended; say so if you want a different seam.
