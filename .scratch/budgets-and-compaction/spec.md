# Budgets and compaction (SHIP-328, P3.4)

Status: ready-for-agent
Source: Linear SHIP-328, milestone "Phase 3: Conversation and runtime"
Branch: `contactsagarbera/ship-328-p34-budgets-and-compaction` (stacked on SHIP-327)

## Problem Statement

The agent loop stops on a step limit and a token limit, but a slow model can still hang a turn, a model can call the same tool with the same arguments forever until the step limit, and a long tool-heavy turn can grow the prompt past what the model accepts. Each of these must end or be handled with a named reason, not a hang or a vendor error.

## Solution

`Budget` gains a time limit and a repeated-call limit. The loop stops with `time_budget` or `loop_detected`. A `Compactor` shrinks the oldest tool results in the working conversation when it nears a size limit, so the loop can continue. Every ending still has a named stop reason.

## User Stories

1. As the runtime, I want a time limit in `Budget`, so a turn cannot run forever.
2. As the runtime, I want the loop to stop with `time_budget` before a model call once the elapsed time has reached the limit.
3. As the runtime, I want a repeated-call limit in `Budget`, so a model stuck repeating itself is caught early.
4. As the runtime, I want the loop to stop with `loop_detected` when the model requests an identical tool call (same name, same arguments) for the limit-th time in one run.
5. As the runtime, I want every tool call of the response that triggered `loop_detected` answered with an error tool result, so the added messages stay well formed.
6. As the runtime, I want calls that differ in name or arguments never counted as identical.
7. As the runtime, I want invalid limits (non-positive time, repeated-call limit below 2) rejected with `DomainError`.
8. As the runtime, I want a `Compactor` that replaces the content of the oldest tool results with a short placeholder when the conversation's size passes its limit.
9. As the runtime, I want the newest messages, the system message, user messages, assistant messages and every tool call/result pairing left intact by compaction.
10. As the runtime, I want compaction to stop as soon as the conversation is under the limit.
11. As the runtime, I want compaction applied before every model call, to the working conversation only, so `LoopResult.added` keeps the full tool output.
12. As the runtime, I want the caller's messages never mutated.
13. As a maintainer, I want new terms in the glossary and `build_app` to use the default compactor.

## Implementation Decisions

- `Budget` adds `max_seconds: float | None = None` and `max_repeated_calls: int = 3` (at least 2).
- `LoopStop` adds `time_budget` and `loop_detected`.
- Time is measured with an injectable monotonic clock (`AgentLoop(monotonic=...)`, default `time.monotonic`), started at the beginning of `run`. The check runs before each model call, next to the token check; an in-flight model call is not interrupted.
- Call identity is the tool name plus its arguments rendered as sorted JSON; counts live for one run.
- On `loop_detected`, the step count includes the step that requested the calls.
- `Compactor(max_chars=48_000, keep_recent=4)`, pure `compact(messages) -> tuple[Message, ...]`. Size is the sum of message content lengths (characters stand in for tokens, as the context builder does). The newest `keep_recent` messages are never touched. Placeholder text is a constant.
- `AgentLoop(compactor=None)`: no compactor means no compaction. Composition passes the default.

## Testing Decisions

- Through the public API only: `AgentLoop.run` with `MockChatModel` scripts and a fake `ToolRunner`; `Compactor.compact` as a pure function. Fake monotonic clock for time.
- Cover every story above. Prior art: `tests/unit/test_runtime_loop.py`, `tests/unit/test_runtime_context.py`.
- `make check` passes; `june.runtime` coverage at least 80%.

## Out of Scope

- Summarising compacted content with the model, exact token counting, interrupting an in-flight model call, per-tool time limits.

## Further Notes

- Linear: SHIP-328.
