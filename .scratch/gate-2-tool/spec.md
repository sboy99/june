# Gate 2: tool (SHIP-333, P4.3)

Status: ready-for-agent
Source: Linear SHIP-333, milestone "Phase 4: Safety"
Branch: `contactsagarbera/ship-333-p43-gate-2-tool` (stacked on SHIP-332)

## Problem Statement

The agent loop runs any tool the model names. Nothing rates a tool's danger, asks anyone before a dangerous one runs, or records the decision.

## Solution

`june.safety` gains a `ToolGate` with a Risk level per tool and an Approval flow. `june.runtime` gains a `GatedToolRunner` that asks a guard before every call and delegates to the real `ToolRunner` only when the guard passes. A denied call becomes an error result the model sees, and repeated denied calls end the loop through the existing Loop guard.

## User Stories

1. As an operator, I want a Risk level per tool name, so I choose which tools are dangerous.
2. As an operator, I want a `low` or `medium` risk tool to run without asking, so safe tools stay fast.
3. As an operator, I want a tool with no configured Risk level treated as `high`, so a new tool is never silently trusted.
4. As an operator, I want a `high` risk tool to ask the Approver before it runs, so a person decides.
5. As an operator, I want a rejection from the Approver to deny the call with `SafetyDenied`.
6. As an operator, I want no Approver configured to mean every `high` call is denied.
7. As an operator, I want an Approver that raises treated as a rejection, so a broken approval flow fails closed.
8. As an operator, I want the Approver given the tool name and arguments, so it can show them.
9. As an operator, I want the Judge, when configured, to review a `medium` risk call before it runs.
10. As the runtime, I want `GatedToolRunner` to list the same specs as the real runner, so the model sees no difference.
11. As the runtime, I want a denied call never to reach the real runner.
12. As the runtime, I want a denied call to become an error result for the model, never a crash.
13. As the runtime, I want the same denied call repeated enough times to end the run as `loop_detected`.
14. As an auditor, I want one log line per decision, and one for each approval outcome, with no raw arguments.

## Implementation Decisions

- `Approver` port in `safety.ports`: `async approve(tool: str, arguments: Mapping[str, Any]) -> bool`.
- `ToolGate(risks, approver=None, judge=None, default_risk="high")`: `async check(name, arguments) -> None`, raising `SafetyDenied`. Uses the shared decision step with a private classifier built per call from the Risk table: `low` and `medium` allow, `high` asks. The subject is the tool name plus its sorted-key JSON arguments; only its digest is logged. An `ask` Decision goes to the Approver; `False`, an exception or no Approver denies.
- `runtime.ports.ToolGuard`: `async check(name, arguments) -> None`, structurally satisfied by `ToolGate`, so runtime never imports safety.
- `GatedToolRunner(inner, guard)` in `june.runtime`. No change to `AgentLoop`.
- ADR 0009 already says gates wrap a `ToolRunner`; this implements it.

## Testing Decisions

- Through `ToolGate.check` with fake Approver and Judge, and through `GatedToolRunner` plus `AgentLoop` with the mock model and a fake runner for the loop-guard story.
- Prior art: `tests/unit/test_runtime_loop.py` (`FakeTools`), `tests/unit/test_safety_input_gate.py`.
- `make check` passes; `june.safety` and `june.runtime` coverage at least 80%.

## Out of Scope

Real tools (Phase 5), a user-facing approval UI, remembering approvals, wiring (SHIP-337), path rules (SHIP-336).

## Further Notes

Linear: SHIP-333.
