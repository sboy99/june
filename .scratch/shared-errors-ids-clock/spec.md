# Spec: Shared errors, ids and clock (SHIP-310, P1.1)

Status: ready-for-agent
Source: Linear SHIP-310, milestone "Phase 1: LLM and shared"

## Problem Statement

Every module in june will raise and handle failures, create identifiers and read the time. Today `shared` has only a thin `JuneError` base and a `PersonaNotFoundError`, plus empty stubs for ids and clock. Without a common error vocabulary, modules invent their own exceptions, the runtime cannot tell a retryable failure from a permanent one, and the CLI cannot print a stable, one-line message. Without an injectable clock and id source, tests that depend on time or random ids are flaky.

## Solution

`june.shared` provides a single error hierarchy rooted at `AgentError`. Each error carries a stable machine-readable `code`, a human message and a `retryable` flag. The hierarchy covers config, persona, domain, adapter (transient and permanent), safety, budget and tool failures. `shared` also provides an id generator and a clock, both usable as injected dependencies so tests can make them deterministic. Existing callers (persona loading, the CLI) move to the new hierarchy without any change in user-visible behaviour.

## User Stories

1. As a runtime author, I want one base error type for every expected failure, so that I can catch agent failures in one place.
2. As a runtime author, I want each error to expose a stable `code`, so that logs, metrics and tests do not depend on message wording.
3. As a runtime author, I want each error to expose a `retryable` flag, so that the loop can decide to retry without inspecting exception types.
4. As a runtime author, I want transient adapter failures to be retryable and permanent ones not, so that a timeout is retried and a bad API key is not.
5. As an adapter author, I want separate transient and permanent adapter error types under a common `AdapterError`, so that I can classify vendor failures at the boundary.
6. As an adapter author, I want to chain the original vendor exception as the cause, so that debugging keeps the full trace.
7. As a CLI user, I want a missing or empty persona file to produce one clear stderr line and a non-zero exit, so that startup failures are easy to read.
8. As a CLI user, I want configuration problems reported as a config error, so that I can tell them apart from persona problems.
9. As a safety author, I want a `SafetyDenied` error, so that a blocked action is distinguishable from a crash and is never retried.
10. As a runtime author, I want a `BudgetExceeded` error, so that exceeding steps, tokens or time ends the turn cleanly and is not retried.
11. As a tooling author, I want a `ToolError`, so that a failed tool call can be reported to the loop as an expected failure.
12. As a domain author, I want a `DomainError`, so that violated business rules are distinct from infrastructure failures.
13. As a developer, I want error `code` values to be unique across the hierarchy, so that a code identifies exactly one error type.
14. As a developer, I want a subclass to inherit a sensible default `code` and `retryable`, so that raising one needs only a message.
15. As a developer, I want to override `retryable` per instance where needed, so that a specific failure can be marked retryable without a new class.
16. As a developer, I want `str(error)` to be the plain message, so that the CLI can print it directly.
17. As a developer, I want a stable id generator in `shared`, so that sessions, turns and other entities get ids the same way everywhere.
18. As a developer, I want generated ids to be unique and URL/file-safe, so that they can be used in logs and file names.
19. As a test author, I want to inject a fake id source, so that tests assert exact ids.
20. As a developer, I want a clock that returns timezone-aware UTC times, so that stored timestamps are unambiguous.
21. As a test author, I want to inject a fixed or steppable clock, so that time-dependent logic is deterministic.
22. As a module author, I want errors, ids and clock importable from `june.shared`, so that I do not reach into submodules.
23. As an architect, I want `shared` to depend on nothing else in june and no vendor SDKs, so that the layer contracts keep passing.
24. As a maintainer, I want the new vocabulary in the glossary, so that code and docs use the same terms.

## Implementation Decisions

- **Naming**: the ticket names the base `AgentError`. The repo currently has `JuneError` and `PersonaNotFoundError`. Decision: rename the base to `AgentError` and `PersonaNotFoundError` to `PersonaNotFound` to match the ticket, and update the CLI and composition root. No alias is kept; there are only two callers. Confirm this rename during implementation, since it changes existing public names.
- **Base error contract**: `AgentError` takes a message and optional keyword-only `retryable` override and `cause` chaining uses normal `raise ... from`. Class-level defaults define `code` (a stable snake_case string) and `retryable` (default false). `str()` returns the message.
- **Hierarchy**: `AgentError` is the root. Direct children: `ConfigError`, `PersonaNotFound`, `DomainError`, `AdapterError`, `SafetyDenied`, `BudgetExceeded`, `ToolError`. `AdapterError` has two children: `TransientAdapterError` (retryable true) and `PermanentAdapterError` (retryable false). A bare `AdapterError` defaults to not retryable.
- **Defaults**: all errors are non-retryable except `TransientAdapterError`. `SafetyDenied` and `BudgetExceeded` are explicitly never retryable.
- **Codes**: each class has a unique, stable code, for example `config_error`, `persona_not_found`, `adapter_transient`. Codes are part of the contract and must not change once released.
- **Ids**: a small `shared` module exposing an id generation function plus an `IdGenerator` protocol-style seam so callers can inject a fake. Ids are opaque, unique, URL/file-safe strings. Exact format is an implementation choice, documented in the module docstring.
- **Clock**: a `Clock` protocol with a `now()` returning an aware UTC datetime, a `SystemClock` implementation, and a `FixedClock` (or equivalent) usable in tests. Domain code stays synchronous and imports no asyncio (ADR 0004).
- **Immutability**: errors and clock/id values are not mutated after construction.
- **Public surface**: everything above is re-exported from `june.shared` with an accurate `__all__`.
- **Layering**: `shared` is the lowest layer. It imports only the standard library. No change to `.importlinter` is expected.
- **Callers**: persona loading raises `PersonaNotFound`; the CLI catches `AgentError`, prints one line to stderr, exits non-zero. Output wording for persona errors is unchanged.
- **Glossary**: add entries for Agent error, Retryable, and Adapter error (transient/permanent), owned by `shared`, in the same PR.
- **ADR**: none required; if the `JuneError` to `AgentError` rename is deemed significant, note it in the PR. It does not contradict any existing ADR.

## Testing Decisions

- A good test exercises external behaviour through the `june.shared` public API only: which exception is raised, its `code`, `retryable`, message and inheritance. It must not inspect private attributes or module internals.
- Single seam: unit tests against `june.shared`. The existing CLI e2e tests remain as the regression check for startup failure output (one stderr line, no traceback, non-zero exit).
- Tests to write:
  - Hierarchy: every named error is an `AgentError`; adapter transient and permanent are `AdapterError`.
  - `retryable`: default per class (transient true, all others false) and per-instance override.
  - `code`: stable value per class and uniqueness across all subclasses (discover subclasses so new errors are covered automatically).
  - `str()` equals the message; cause chaining is preserved.
  - Ids: unique across many calls; safe characters; injected fake is honoured.
  - Clock: system clock returns an aware UTC datetime; fixed clock returns the set time and can be advanced.
- Prior art: `tests/e2e/test_cli.py` for style (behavioural assertions, pytest markers) and `tests/contract/test_architecture.py` for the architecture check. Add `tests/unit/` for the new tests, following the Arrange-Act-Assert pattern and descriptive names.
- Done when: `make check` passes, unit tests cover the hierarchy and the `retryable` flag, and coverage on `shared` meets the repo's 80% minimum.

## Out of Scope

- Retry or backoff logic that consumes `retryable` (belongs to runtime).
- Mapping specific vendor exceptions to transient or permanent (belongs to each adapter).
- Logging or formatting of errors beyond the CLI one-liner (observability).
- Async clock or sleep helpers.
- Persisting ids or timestamps.
- Changes to `.importlinter` contracts.

## Further Notes

- Linear: SHIP-310, project June, milestone "Phase 1: LLM and shared". Branch: `contactsagarbera/ship-310-p11-shared-errors-ids-and-clock`.
- The ticket's "AdapterError (transient/permanent)" is modelled as two subclasses rather than a flag, so callers can catch either one and the `retryable` default follows from the type.
- Later Phase 1 tickets (the llm port, the runtime loop) are expected to depend on these types.
