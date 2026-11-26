# Embedder adapters (SHIP-320, P2.3)

Status: ready-for-agent
Source: Linear SHIP-320, milestone "Phase 2: Memory"
Branch: `contactsagarbera/ship-320-p23-embedder-adapters` (stacked on SHIP-319)

## Problem Statement

`june.memory.ports.Embedder` has a written contract but no implementation. Recall, remember and the contract suites (P2.5, P2.7) need an embedder that works offline and deterministically for tests and local runs, and one that calls a real embeddings API.

## Solution

Two adapters in `june.memory.adapters`:

- `HashingEmbedder`: offline, deterministic, no network. Hashes tokens into a fixed number of buckets and L2-normalizes the result.
- `OpenAICompatibleEmbedder`: calls an OpenAI-compatible `/embeddings` endpoint, maps SDK errors to adapter errors, and exposes an `EmbedderInfo` so stored vectors name the model that made them.

## User Stories

1. As a test author, I want a hashing embedder with no network, so that memory tests run offline.
2. As a test author, I want the same text to give the same vector across calls and processes, so that tests are stable.
3. As a use-case author, I want similar texts (shared words) to score closer than unrelated ones, so that recall tests mean something.
4. As an adapter user, I want vectors to be unit length (or all zero for text with no tokens), so that dot product equals cosine similarity.
5. As an operator, I want `info` to carry a name, a version and the dimension count, so that a model change is detectable.
6. As an operator, I want the hashing embedder's version to change if its algorithm changes, so that old vectors are flagged stale.
7. As an adapter user, I want an empty batch to return `[]` without any call, so that callers need no special case.
8. As an adapter user, I want one vector per text in input order, each with `info.dimensions` finite floats.
9. As an adapter user, I want blank text accepted (a zero vector for hashing; passed through for the API), so that callers can filter.
10. As an operator, I want the API embedder to take model, API key, base URL, dimensions, timeout and retry count, so that I can point it at any compatible server.
11. As an operator, I want the API embedder's `info.name` to be the model name and `info.version` a fixed string, so that switching models changes identity.
12. As an adapter user, I want the API embedder to reject a response whose vector count or length differs from the request, with `PermanentAdapterError`, so that bad data never reaches the index.
13. As an adapter user, I want response vectors reordered by their `index` field, so that order always matches the input.
14. As an adapter user, I want 408, 409, 429, 5xx and connection errors raised as `TransientAdapterError`, and other failures as `PermanentAdapterError`, after the SDK's bounded retries.
15. As a security reviewer, I want error text never to contain the API key, request text or response body.
16. As an architect, I want the OpenAI SDK imported only in the adapter module, so that the import contracts keep passing.
17. As a maintainer, I want both adapters to satisfy the `Embedder` Protocol structurally, checked by mypy.

## Implementation Decisions

- Modules: `memory/adapters/hashing_embedder.py`, `memory/adapters/openai_embedder.py`. Adapters are not re-exported from `june.memory` (contract 4 keeps adapters private); tests import the modules directly, as for `llm`.
- `HashingEmbedder(dimensions=256)`: tokens are `normalize_text(text).split()`; each token hashes with SHA-256 to a bucket index and a sign (one bit); counts accumulate; the vector is divided by its L2 norm. `info` = `EmbedderInfo("hashing", "1", dimensions)`. Pure, so `embed` is `async` but does no I/O. A dimension below 1 raises `DomainError` (from `EmbedderInfo`).
- `OpenAICompatibleEmbedder(model, api_key, dimensions, base_url=None, timeout_seconds=30.0, max_retries=2, http_client=None)`: uses `openai.AsyncOpenAI().embeddings.create(model=..., input=[...], dimensions=...)` only when `dimensions` is given by the caller; always validates returned lengths. `info` = `EmbedderInfo(model, "1", dimensions)`.
- Error translation reuses the same rules as the chat adapter. Duplicating the small function is accepted: `llm.adapters` and `memory.adapters` are same-level modules and may not import each other, and `june.shared` is for primitives, not vendor mapping.
- No settings or composition wiring (P2.7).

## Testing Decisions

- Test through the public adapter classes and the `Embedder` Protocol. Fake the endpoint with `httpx2.MockTransport`, as in `tests/unit/test_llm_openai_adapter.py` (shared fake in `tests/openai_fakes.py`).
- Hashing: determinism, unit length, similarity ordering, empty batch, blank text, order, dimensions, bad dimensions.
- API: request body, ordering by index, count and length mismatch, each transient status, permanent status, connection error, no key leakage, empty batch makes no request.
- `make check` passes; coverage of both modules at least 80%.

## Out of Scope

- Settings keys and composition-root selection of an embedder (P2.7).
- Contract suite shared across adapters (P2.7).
- Batching beyond one request, caching, and local model embedders.

## Further Notes

- Linear: SHIP-320.
