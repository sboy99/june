# Mock model adapter (SHIP-314)

Status: ready-for-agent

## Problem Statement

Every later test (runtime, e2e) and every offline run needs a `ChatModel` that is deterministic, free and needs no network or key. Today the port has no implementation, and `llm_provider=mock` resolves to nothing.

## Solution

`june.llm.adapters.mock.MockChatModel` implements `ChatModel`. With a script it replays prepared steps in order (replies, tool calls or errors) and records every call for assertions. Without a script it echoes the last user message, so `llm_provider=mock` works offline.

## User Stories

1. As a test author, I want to give a list of replies and get them back in order, so that a conversation is fully predictable.
2. As a test author, I want a plain string in the script to mean a normal text reply, so that simple scripts stay short.
3. As a test author, I want to script a full `ChatResponse` (tool calls, stop reason, usage), so that I can drive the tool loop.
4. As a test author, I want to script an error step (any `AgentError`), so that I can test retry and failure handling.
5. As a test author, I want to read back the messages, tools and `max_tokens` of every call, so that I can assert what the runtime sent.
6. As a test author, I want a clear `PermanentAdapterError` when the script runs out, so that a test never hangs or silently repeats.
7. As an operator, I want `llm_provider=mock` to answer by echoing the last user message, so that I can run offline.
8. As an adapter author, I want the mock to meet the `ChatModel` contract (empty messages rejected, valid response), so that it is a faithful stand-in.
9. As an architect, I want the mock under `llm/adapters` importing only the standard library, `june.llm` and `june.shared`, so that layer contracts pass.

## Implementation Decisions

- File `src/june/llm/adapters/mock.py`; class `MockChatModel(script: Iterable[ScriptStep] | None = None, *, model: str = "mock")`; `ScriptStep = str | ChatResponse | AgentError`.
- A string step becomes an `end_turn` response with usage derived from whitespace-separated word counts, so values are deterministic.
- An `AgentError` step is raised when reached (it consumes the step).
- `calls` property returns an immutable tuple of recorded `MockCall(messages, tools, max_tokens)`.
- Script exhausted: `PermanentAdapterError("mock script exhausted")`. Empty messages: `PermanentAdapterError`, checked before consuming a step.
- Echo mode (no script): reply is `echo: <last user message>`, or `echo: ` when there is none.
- Wiring into `composition.py` is SHIP-317, not here.

## Testing Decisions

- Scripted replies in order; string vs `ChatResponse` steps; error step raised; exhaustion error; empty messages rejected without consuming; calls recorded; echo mode; determinism (two runs equal).
- Prior art: `tests/unit/test_llm_ports.py`.
- Done when: `make check` passes.
