# Red-team test set and wiring (SHIP-337, P4.7)

Status: ready-for-agent
Source: Linear SHIP-337, milestone "Phase 4: Safety"
Branch: `contactsagarbera/ship-337-p47-red-team-test-set-and-wiring` (stacked on SHIP-336)

## Problem Statement

The four Gates and Protected paths exist but are not connected. The Phase 4 exit check (prompt injection, secret leak and persona overwrite are blocked, and every decision is logged) cannot pass.

## Solution

`build_app` wires the Gates: the Input gate and End-loop gate around `ChatService`, the Memory-write gate into memory writes and the Skill store, and a Tool gate exposed on the `App` for the Phase 5 tool runner. A new stop reason, `safety_denied`, tells the caller a Gate blocked the turn. A red-team end-to-end test set proves the exit check on the mock LLM.

## User Stories

1. As a user, I want a message that tries to override the agent's instructions refused with a `safety_denied` reply, so injection never reaches the model.
2. As a user, I want a refused message not saved as a Turn and the model never called.
3. As a user, I want a secret in the model's reply replaced with `[REDACTED]`, in the reply and in the saved Turn.
4. As a user, I want an empty or oversize reply refused with `safety_denied`.
5. As an operator, I want a Fact that contains a secret never stored.
6. As an operator, I want a remembered text that orders an overwrite of the Persona never stored.
7. As an operator, I want a tool call that writes to `persona/` denied by the Tool gate, and the model told so.
8. As an operator, I want the Tool gate built by composition and available as `App.tool_gate`, so the Phase 5 runner can be wrapped with `GatedToolRunner`.
9. As an operator, I want every Gate decision logged with its gate name, decision, risk and reason, and never the raw text.
10. As an operator, I want ordinary chat to behave exactly as before.
11. As a maintainer, I want `LoopStop.SAFETY_DENIED` and `TextGuard` documented in the glossary.
12. As a maintainer, I want the red-team cases in one table-driven test file, so a new attack is one new row.

## Implementation Decisions

- `LoopStop.SAFETY_DENIED = "safety_denied"`. `ChatReply` for it has an empty reply, the unchanged session and `error_code="safety_denied"`. It is not a saved stop.
- `runtime.ports.TextGuard`: `async check(text) -> str`. `ChatService` takes optional `input_guard` and `reply_guard`; both are satisfied structurally by the Input gate and End-loop gate. The reply guard's returned (redacted) text is what is returned and saved.
- Composition builds `ProtectedPaths` from the Persona path and the skills directory, a `MemoryWriteGate` for `RememberFact`, `RememberEpisode` and a `GuardedSkillStore`, an `InputGate`, an `EndLoopGate` and a `ToolGate` (no tool risks yet, so every tool is high risk and denied until an Approver exists).
- No Judge or Approver adapter is wired; they stay optional ports.

## Testing Decisions

- End-to-end through `build_app` and `ChatService` on the mock LLM, plus `GatedToolRunner` with `app.tool_gate`. Assert on replies, stored state, whether the model was called, and decision log lines.
- Prior art: `tests/e2e/test_chat_on_mock_llm.py`. Existing tests must pass unchanged.
- `make check` passes; coverage stays at least 80%.

## Out of Scope

Real tools and their risk levels (Phase 5), a Judge adapter, an approval UI, a real model.

## Further Notes

This closes Phase 4. Linear: SHIP-337.
