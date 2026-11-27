# ADR 0011: Gates fail closed, except end-loop

- Status: accepted

## Context
Safety Gates call checkers (rules, a model Judge) that can error or time out. Each Gate issue would otherwise choose its own behaviour on failure.

## Decision
When a checker errors, the `input`, `tool` and `memory_write` Gates return `deny`. The `end_loop` Gate returns `allow` and logs a warning, because it only guards the final answer and a denial there would drop a finished turn. `ask` is treated as `deny` until a confirmation flow exists. The rule lives in `june.safety.policy` and is mirrored in `docs/ARCHITECTURE.md`; a test keeps them in step.

## Consequences
A broken checker can block legitimate actions, never let a dangerous one through. The end-loop exception is explicit and reviewable.

## Alternatives considered
Failing open everywhere (a broken checker silently disables safety). Failing closed everywhere (a Judge outage would discard completed answers).
