# Agent loop state machine (SHIP-327, P3.3)

Status: ready-for-agent
Source: Linear SHIP-327, milestone "Phase 3: Conversation and runtime"
Branch: `contactsagarbera/ship-327-p33-agent-loop-state-machine` (stacked on SHIP-326)

## Problem Statement

Nothing drives a conversation to an answer. A Chat model can ask for tools, but there is no code that runs them, feeds results back, stops, or decides what to do when something fails. Tools and safety Gates do not exist yet and must plug in later without changing the loop.

## Solution

`june.runtime` gains an `AgentLoop`. Given the messages for a Turn, it asks the model, runs any requested tools through a `ToolRunner` port, feeds results back, and repeats until the model gives a final answer or a Budget ends the Turn. Every ending has a named stop reason. Errors are caught at the loop and handled in one of three ways: retried, returned to the model as an error tool result, or ended with a stop reason.

## User Stories

1. As the runtime, I want `run(messages)` to return a `LoopResult` with the stop reason, the reply text, the messages the loop added, the step count and the summed usage.
2. As the runtime, I want a final answer (`end_turn`) to end the loop with stop reason `answered`.
3. As the runtime, I want requested tool calls run through the `ToolRunner` port, their results appended as tool messages in call order, then the model asked again.
4. As the runtime, I want the tool specs offered to the model on every call, and none when no runner is configured.
5. As the runtime, I want a tool that raises an expected `AgentError` (for example `ToolError` or `SafetyDenied`) to produce an error tool result carrying the error code, so the model can react; the loop continues and does not retry the tool.
6. As the runtime, I want an unexpected exception from a tool turned into a generic error tool result, with the details logged and not shown to the model.
7. As the runtime, I want a call to an unknown tool, or any call when no runner exists, answered with an error tool result.
8. As the runtime, I want error text redacted of secrets before it reaches the model.
9. As the runtime, I want a retryable model failure retried up to a set count, and then ended with stop reason `model_error` and the error code.
10. As the runtime, I want a non-retryable model failure ended at once with stop reason `model_error`.
11. As the runtime, I want the loop to stop with `max_steps` when the step limit is reached, with every tool call in the added messages answered by a result.
12. As the runtime, I want the loop to stop with `token_budget` before a model call when summed usage has reached the token limit.
13. As the runtime, I want a model reply cut off by its own token limit (`max_tokens`) to end with stop reason `truncated` and the partial text.
14. As the runtime, I want an empty message list rejected with `DomainError`, and invalid Budget values rejected.
15. As the runtime, I want the input messages left untouched.
16. As an architect, I want the loop to depend only on ports (`ChatModel`, `ToolRunner`) so tools and gates plug in later through composition.
17. As a maintainer, I want `build_app` to expose an `agent_loop` using the chat model and no tools, and new terms in the glossary and an ADR for where the tool port lives.

## Implementation Decisions

- `Budget(max_steps=10, max_total_tokens=None)` frozen; steps must be at least 1, tokens at least 1 when set. Time limits are out of scope.
- `AgentLoop(model, tools=None, budget=Budget(), max_model_retries=2)`; one async `run(messages) -> LoopResult`. Stateless between runs.
- `LoopStop` is a string enum: `answered`, `max_steps`, `token_budget`, `truncated`, `model_error`.
- `LoopResult` is frozen: `stop`, `reply`, `added` (tuple of Messages), `steps`, `usage`, `error_code`. `reply` is empty unless `answered` or `truncated`.
- A step is one model call plus the tools it requested.
- `ToolRunner` port lives in the runtime, not in `tooling`: `tooling` and `llm` are siblings and cannot import each other, so a tooling port cannot mention `ToolSpec` or `ToolCall`. Composition adapts tooling into it later. Recorded as ADR 0009.
- `ToolRunner` exposes `specs` and an async `run(call) -> ToolResult`. Expected failures raise `AgentError` subclasses. Gates later wrap a runner and raise `SafetyDenied`.
- Tool calls in one response run one after another, in order.
- Only `AgentError` from the model is handled; other exceptions are bugs and propagate. `CancelledError` always propagates.
- Retry has no sleep: adapters already back off internally.
- Log tool and model failures through `june.observability.get_logger`; error text goes through `redact_text`.

## Testing Decisions

- Drive the loop through its public API with `MockChatModel` scripts and a fake `ToolRunner`; assert on `LoopResult` and on the calls the mock recorded. No assertions on private helpers.
- Cover every story above. Prior art: `tests/unit/test_llm_mock_adapter.py`.
- `make check` passes; coverage of `june.runtime` at least 80%.

## Out of Scope

- Real tools, safety Gates, MCP, sub-agents, time budgets, parallel tool execution, streaming, memory hand-off after a Turn, a CLI chat command.

## Further Notes

- Linear: SHIP-327.
