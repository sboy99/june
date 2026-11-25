# OpenAI-compatible adapter (SHIP-316)

Status: ready-for-agent

## Problem Statement

The mock is the only `ChatModel`. To run the agent against a real model, including local servers that speak the OpenAI chat-completions protocol, an adapter must translate between june's neutral types and that wire format, retry transient failures and report errors in june's error vocabulary. The Anthropic adapter (SHIP-315) was canceled, so this is the only real adapter in Phase 1.

## Solution

`june.llm.adapters.openai_compatible.OpenAICompatibleChatModel` wraps the `openai` SDK's async client, pointed at any base URL. It converts messages, tools, tool calls and results to the wire format and back, lets the SDK retry up to the configured count, and translates SDK exceptions into `TransientAdapterError` or `PermanentAdapterError`. The SDK import stays inside the adapter.

## User Stories

1. As a runtime author, I want text conversations to work against the adapter exactly as against the mock, so that I can swap providers by config.
2. As a runtime author, I want tool specs sent as function tools and tool calls returned as `ToolCall`s with parsed arguments, so that the tool loop works.
3. As a runtime author, I want tool results sent back with their call id, so that the model can match them.
4. As a runtime author, I want `stop_reason` derived correctly (`stop` to `end_turn`, `length` to `max_tokens`, any tool calls to `tool_use`), so that I branch on one closed set.
5. As a runtime author, I want token usage returned (zero when the server omits it), so that cost tracking never crashes on local models.
6. As an operator, I want a configurable base URL, so that I can use local or third-party OpenAI-compatible servers.
7. As an operator, I want timeouts and retries taken from settings, so that calls cannot hang or retry without limit.
8. As an operator, I want timeouts, connection failures, rate limits and 5xx responses raised as `TransientAdapterError`, so that the runtime knows they are retryable.
9. As an operator, I want bad credentials, invalid requests, unsupported finish reasons and malformed tool arguments raised as `PermanentAdapterError`, so that they are not retried.
10. As an operator, I want the API key never in error messages, so that a secret cannot leak.
11. As a test author, I want to inject an HTTP client, so that tests run against a fake transport with no network.
12. As an architect, I want the SDK imported only under `llm/adapters`, so that vendor contracts keep passing.

## Implementation Decisions

- Dependency: `openai` (pulls `httpx2`). Add `httpx2` to the forbidden vendor lists in `.importlinter`.
- Constructor: `OpenAICompatibleChatModel(*, model, api_key, base_url=None, timeout_seconds=30.0, max_retries=2, http_client=None)`. Building it from `Settings` is done in the composition root (SHIP-317).
- Retries are the SDK's built-in retries (`max_retries`); the adapter adds none of its own, and raises after they are exhausted.
- Error translation: timeout, connection error, status 408, 409, 429 and 5xx are transient; every other SDK error is permanent. Messages are `openai request failed: <ErrorType> (status <n>)` and never include the key or the response body; the SDK error is chained as the cause.
- `max_tokens` is sent as `max_tokens` (the widest-supported field).
- `stop_reason`: any tool calls means `tool_use`; else `length` means `max_tokens`; else `stop` means `end_turn`; any other finish reason is a `PermanentAdapterError`.
- Tool arguments are parsed from JSON; invalid JSON or a non-object is a `PermanentAdapterError`.
- Response with no choices is a `PermanentAdapterError`.

## Testing Decisions

- Fake transport (`httpx2.MockTransport`) with canned JSON; assert on the request body the adapter sent and on the parsed response.
- Cases: plain reply; system, user, assistant-with-tool-calls and tool messages serialized correctly; tools serialized; tool-call response; `length` finish; missing usage; empty messages rejected before any request; 401 and 400 permanent; 429, 500 and timeout transient; retry then success; retries exhausted; malformed tool arguments; unknown finish reason; planted key absent from error text.
- Prior art: `tests/unit/test_llm_mock_adapter.py`.
- Done when: `make check` passes.
