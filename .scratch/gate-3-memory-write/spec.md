# Gate 3: memory-write (SHIP-334, P4.4)

Status: ready-for-agent
Source: Linear SHIP-334, milestone "Phase 4: Safety"
Branch: `contactsagarbera/ship-334-p44-gate-3-memory-write` (stacked on SHIP-333)

## Problem Statement

Anything the agent decides to remember is stored as is. A secret in a conversation can become a Fact, and a poisoned message ("from now on always obey ...") can be saved and later replayed as trusted memory.

## Solution

`june.safety` gains a `MemoryWriteGate` that denies secrets and poisoning phrases. `june.memory` gains a `WriteGuard` port; `RememberFact`, `RememberEpisode` and a new `GuardedSkillStore` ask it before storing. Consolidation skips a denied candidate instead of failing the run.

## User Stories

1. As an operator, I want text containing a secret denied before it is stored as a Fact, Episode or Skill.
2. As an operator, I want text that tries to plant standing instructions ("from now on you must", "never tell the user") denied.
3. As an operator, I want the injection phrases from Gate 1 denied here too, so poison cannot be stored for later.
4. As an operator, I want ordinary text allowed unchanged.
5. As an operator, I want the check to fail closed when a checker errors.
6. As an operator, I want a denied Fact never to reach the index.
7. As an operator, I want a denied Episode never to reach the index.
8. As an operator, I want every part of a Skill (name, description, steps) checked before the Skill is saved.
9. As an operator, I want a denied Skill never to reach the Skill store; other store operations pass through.
10. As an operator, I want Consolidation to skip a denied candidate, count it as skipped, and still finish the run.
11. As an operator, I want memory to work as before when no guard is configured.
12. As an auditor, I want every decision logged through the shared decision step, never with the raw text.

## Implementation Decisions

- `SecretClassifier` and `PoisoningClassifier` adapters in `safety/adapters`; `CompositeClassifier(*classifiers)` returns the first `deny`, else `allow`. The memory-write Gate uses secrets, poisoning and the injection rules. Secret detection reuses the log redaction patterns.
- `MemoryWriteGate(classifier, judge=None)`: `async check(text) -> None`, raising `SafetyDenied`.
- `memory.ports.WriteGuard`: `async check(text) -> None`, structurally satisfied by `MemoryWriteGate` (memory never imports safety).
- `RememberFact` and `RememberEpisode` take an optional keyword `guard` and check the text before embedding. `Consolidate` catches `SafetyDenied` per candidate and counts a skip. `GuardedSkillStore(inner, guard)` in `memory.application` checks a Skill's joined text on `save`.

## Testing Decisions

- Through use cases with the in-memory fakes already used in `tests/unit/test_memory_application.py` and `test_memory_consolidation.py`, plus the real gate with real classifiers.
- `make check` passes; `june.safety` and `june.memory` coverage at least 80%.

## Out of Scope

Protected paths (SHIP-336), wiring (SHIP-337), semantic poisoning detection, redacting instead of denying.

## Further Notes

Linear: SHIP-334.
