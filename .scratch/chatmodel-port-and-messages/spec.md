# ChatModel port and message types (SHIP-313)

Status: ready-for-agent

## Problem Statement

`llm/ports.py` holds an empty `ChatModel` stub. The mock, OpenAI-compatible adapters and the runtime cannot be built against it: there is no shared shape for messages, tool calls, usage or stop reasons, and no statement of what an adapter must return or which errors it may raise.

## Solution

`june.llm.ports` defines immutable, vendor-neutral message types and an async `ChatModel` Protocol with a written contract. Adapters translate vendor formats to and from these types; the runtime sees only these types. The contract is precise enough that the later contract test suite (SHIP-317) can be written from it.

## User Stories

1. As a runtime author, I want typed messages with roles `system`, `user`, `assistant` and `tool`, so that I build a conversation without vendor formats.
2. As a runtime author, I want an assistant message to carry zero or more tool calls (id, name, arguments), so that the model can ask for tools.
3. As a runtime author, I want a tool message to carry a tool result (call id, content, error flag), so that I can feed tool output back.
4. As a runtime author, I want malformed messages (tool call on a user message, tool message without result) rejected at construction, so that bugs surface early.
5. As a runtime author, I want a `ChatResponse` with the assistant message, `stop_reason`, `usage` and model name, so that I can branch on why the model stopped and track cost.
6. As a runtime author, I want `stop_reason` limited to `end_turn`, `tool_use` and `max_tokens`, so that I handle a closed set.
7. As a runtime author, I want tool definitions as `ToolSpec` (name, description, JSON-schema parameters), so that I advertise tools vendor-neutrally.
8. As an adapter author, I want a documented contract (return shape, invariants, allowed errors), so that every adapter behaves the same.
9. As an adapter author, I want transient failures raised as `TransientAdapterError` and permanent ones as `PermanentAdapterError`, so that the runtime knows what to retry.
10. As a test author, I want any class with the right async method to satisfy `ChatModel` structurally, so that fakes need no inheritance.
11. As an architect, I want `llm.ports` to import only the standard library and `june.shared`, so that layer contracts keep passing.
12. As a maintainer, I want new terms in the glossary, so that code and docs use the same words.

## Implementation Decisions

- Standard-library frozen dataclasses (no pydantic) in `june/llm/ports.py`; re-exported from `june.llm`.
- Types: `Role`, `StopReason` (Literals), `ToolCall`, `ToolResult`, `Message`, `ToolSpec`, `Usage`, `ChatResponse`, `ChatModel`.
- `Message` invariants (checked in `__post_init__`, raising `ValueError`): `tool_calls` only on `assistant`; `tool_result` present exactly when role is `tool`. Convenience constructors: `Message.system/user/assistant/tool`.
- Mapping fields (`arguments`, `parameters`) are copied into read-only mappings so messages are truly immutable.
- `Usage` holds non-negative `input_tokens` and `output_tokens` and a `total_tokens` property.
- `ChatModel.complete(messages, *, tools=(), max_tokens=None) -> ChatResponse`, async.
- Contract, written in the Protocol docstring: response message has role `assistant`; `stop_reason == "tool_use"` exactly when the message has tool calls; at least one input message is required; tool call ids are unique within a response; adapters retry transient failures internally up to the configured retry count and then raise; only `TransientAdapterError` and `PermanentAdapterError` escape (never vendor exceptions); invalid requests raise `PermanentAdapterError`; API keys never appear in error text.
- `ChatResponse` enforces its own invariants on construction (assistant role, `tool_use` iff tool calls, unique ids), so every adapter gets them for free.
- No change to `.importlinter`.

## Testing Decisions

- Construction and invariants of each type; immutability of frozen fields and of mapping contents.
- `Usage.total_tokens`; negative tokens rejected.
- A minimal fake `ChatModel` with no inheritance satisfies the Protocol (`runtime_checkable` not required; verified by mypy-checked assignment and a runtime call).
- Exports from `june.llm`.
- Architecture contracts pass (`make arch`).
- Prior art: `tests/unit/test_shared_*.py`.
- Done when: `make check` passes and the contract is written down in the Protocol docstring.
