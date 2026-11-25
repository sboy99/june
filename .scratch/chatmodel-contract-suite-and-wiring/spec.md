# ChatModel contract suite and wiring (SHIP-317)

Status: ready-for-agent

## Problem Statement

The `ChatModel` contract is written down, but nothing proves every adapter meets it, and `composition.py` does not yet build a model from `llm_provider`. The Phase 1 exit check cannot pass.

## Solution

One contract test suite runs the same scenarios against each adapter through a small harness: the mock, the OpenAI-compatible adapter on a fake transport, and the OpenAI-compatible adapter against a live endpoint (skipped unless live credentials are in the environment). `composition.py` builds the chosen adapter once, from settings, and exposes it on `App` as the single shared client.

## User Stories

1. As an adapter author, I want one suite that every adapter must pass, so that the contract is executable.
2. As a maintainer, I want a new adapter to need only a harness, not new tests, so that adding one is cheap.
3. As a maintainer, I want live-endpoint tests skipped without credentials, so that `make check` needs no network or key.
4. As a runtime author, I want `App.chat_model` built from `llm_provider`, so that I never construct adapters myself.
5. As a runtime author, I want exactly one client per app, so that connections and retries are shared.
6. As an operator, I want `llm_provider=mock` to need no key and `openai` to use my key, model, base URL, timeout and retry settings, so that config alone picks the model.
7. As a test author, I want the OpenAI fake server shared between unit and contract tests, so that it is not duplicated.

## Implementation Decisions

- Contract suite: `tests/contract/test_chat_model_contract.py`; harnesses are parametrized fixtures offering `model_for(outcome)` for outcomes `text`, `tool_call`, `transient_error`, `permanent_error`; a harness skips outcomes it cannot produce (live supports `text` only).
- Scenarios: text reply meets response invariants and has role `assistant`; tool-call reply has `stop_reason == "tool_use"` and unique call ids; usage non-negative; empty messages raise `PermanentAdapterError`; transient outcome raises `TransientAdapterError` with `retryable`; permanent outcome raises `PermanentAdapterError` without `retryable`; every raised error is an `AdapterError`; error text never contains the planted key; an adapter is usable as `ChatModel` and calls are repeatable.
- Live harness reads `JUNE_LIVE_LLM_API_KEY`, `JUNE_LIVE_LLM_MODEL` and optional `JUNE_LIVE_LLM_BASE_URL`.
- Shared fake server moves to `tests/openai_fakes.py`; the unit test imports it.
- `composition.py`: `build_chat_model(settings) -> ChatModel`; `App` gains `chat_model`; built once in `build_app`. A missing key for `openai` raises `ConfigError` (already prevented by settings validation; this guards the type).
- ADR not needed: no decision contradicts an existing one.

## Testing Decisions

- Contract suite as above across mock and fake-transport OpenAI; live case collected and skipped.
- Composition: mock provider yields `MockChatModel`; `openai` yields `OpenAICompatibleChatModel`; `App` holds one instance.
- Done when: `make check` passes, which is the Phase 1 exit check (contract suite green, adapter errors are `AdapterError`s, log filter test from SHIP-311 still green).
