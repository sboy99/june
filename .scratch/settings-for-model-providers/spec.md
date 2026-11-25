# Settings for model providers (SHIP-312)

Status: ready-for-agent

## Problem Statement

`config.py` knows only `llm_provider` (a free string). The model adapters of Phase 1 (mock, OpenAI-compatible) need a model name, credentials, a timeout and a retry count. Without validated settings, a typo in the provider name or a missing API key surfaces late, deep inside an adapter call, and an API key could leak into logs or error messages.

## Solution

`Settings` gains model-provider fields, all read from `JUNE_*` environment variables. `llm_provider` becomes a closed set. The API key is a secret type that never prints its value. Cross-field rules (a real provider needs a model and a key) are checked when settings load, so startup fails with one clear line. `.env.example` lists every setting.

## User Stories

1. As an operator, I want `llm_provider` limited to known providers (`mock`, `openai`), so that a typo fails at startup.
2. As an operator, I want to set the model name with `JUNE_LLM_MODEL`, so that I choose the model without code changes.
3. As an operator, I want to set the API key with `JUNE_LLM_API_KEY`, so that credentials stay out of code and config files.
4. As an operator, I want the API key never shown in `repr`, `str`, logs or error messages, so that a secret cannot leak.
5. As an operator, I want an optional `JUNE_LLM_BASE_URL`, so that I can target any OpenAI-compatible server.
6. As an operator, I want `JUNE_LLM_TIMEOUT_SECONDS` and `JUNE_LLM_MAX_RETRIES` with safe defaults and bounds, so that calls cannot hang forever or retry without limit.
7. As an operator, I want startup to fail with one `ConfigError` line when a real provider has no API key or no model, so that I fix it before serving traffic.
8. As an operator, I want the mock provider to need no key, so that development and tests work offline.
9. As an operator, I want `.env.example` to list every setting, so that I know what can be configured.
10. As a maintainer, I want a test that fails when a setting is missing from `.env.example`, so that the file never drifts.

## Implementation Decisions

- Fields: `llm_provider: Literal["mock", "openai"] = "mock"`, `llm_model: str = "mock"`, `llm_api_key: SecretStr | None = None`, `llm_base_url: str | None = None`, `llm_timeout_seconds: float` (default 30, greater than 0, at most 600), `llm_max_retries: int` (default 2, 0 to 10).
- Anthropic is not a provider (SHIP-315 is canceled); adding one later extends the `Literal`.
- A `model_validator` rejects `openai` without an API key or with a blank model. Error text names the setting, never the value.
- `load_settings` keeps its single-line `ConfigError` shape; errors with no field location (model validators) must still render cleanly.
- No new module and no layering change; `config.py` stays the only environment reader.
- Immutability: settings are frozen.

## Testing Decisions

- Defaults load with no environment (mock provider, no key).
- Unknown provider, non-positive timeout, out-of-range retries and malformed numbers each raise `ConfigError` naming the setting, on one line.
- `openai` without key, and with blank model, raises `ConfigError`.
- A planted API key is absent from `repr(settings)`, `str(settings)` and every `ConfigError` message.
- `.env.example` contains a `JUNE_<FIELD>` line for every `Settings` field.
- Prior art: `tests/unit/test_config.py`.
- Done when: `make check` passes and every bullet above is covered.
