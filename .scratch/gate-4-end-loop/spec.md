# Gate 4: end-loop (SHIP-335, P4.5)

Status: ready-for-agent
Source: Linear SHIP-335, milestone "Phase 4: Safety"
Branch: `contactsagarbera/ship-335-p45-gate-4-end-loop` (stacked on SHIP-334)

## Problem Statement

The final answer of the agent loop goes to the user as the model wrote it. It can leak a secret the model saw, be empty, or be huge.

## Solution

`june.safety` gains an `EndLoopGate`. It redacts secrets in the reply, denies an empty or oversize reply, and may ask a Judge, before the reply is returned. Per ADR 0011 it fails open: if a checker breaks, the already-redacted reply is returned and a warning is logged.

## User Stories

1. As a user, I want secrets in a reply replaced with `[REDACTED]`, so a leaked key never reaches me.
2. As a user, I want a reply with no secret returned unchanged.
3. As an operator, I want an empty or whitespace-only reply denied with `SafetyDenied`.
4. As an operator, I want a reply longer than a configured limit denied.
5. As an operator, I want the limit configurable, with a default of 8000 characters, and a limit below 1 rejected with `DomainError`.
6. As an operator, I want redaction to happen before the length check, so a reply is judged as the user would see it.
7. As an operator, I want an optional Judge consulted on medium-risk replies.
8. As an operator, I want a Judge `deny` to deny the reply.
9. As an operator, I want a broken checker to return the redacted reply and log a warning (fail open, ADR 0011).
10. As an auditor, I want one log line per decision, never with the reply text.

## Implementation Decisions

- `LengthClassifier(max_chars)` adapter: empty is `deny`/`low`, longer than the limit is `deny`/`medium`, longer than half the limit is `allow`/`medium` (so a Judge reviews it), else `allow`/`low`.
- `EndLoopGate(max_chars=8000, judge=None, classifier=None)`: `async check(reply) -> str` redacts with the same patterns as log redaction, runs the shared decision step, returns the redacted reply or raises `SafetyDenied`.
- Not wired yet (SHIP-337).

## Testing Decisions

- Through `EndLoopGate.check` with fake Judge and broken Classifier; assert on returned text, errors and log lines.
- `make check` passes; `june.safety` coverage at least 80%.

## Out of Scope

Wiring, rewriting a denied reply, streaming replies.

## Further Notes

Linear: SHIP-335.
