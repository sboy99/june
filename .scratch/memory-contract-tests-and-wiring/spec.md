# Memory contract tests and wiring (SHIP-324, P2.7)

Status: ready-for-agent
Source: Linear SHIP-324, milestone "Phase 2: Memory"
Branch: `contactsagarbera/ship-324-p27-memory-contract-tests-and` (stacked on SHIP-323)

Phase 2 exit check: domain tests run with no I/O; adapter contract tests pass; consolidation can be re-run safely (idempotent, locked).

## Problem Statement

Each memory adapter is tested only by its own unit tests, so the port contracts are not proven for every adapter, and `build_app` does not build any memory: the runtime cannot reach the index, embedder or use cases.

## Solution

- One contract suite per port in `tests/contract/`, parametrized over every adapter of that port, written from the port docstrings: `Embedder`, `VectorIndex`, `SkillStore`.
- Memory settings and wiring: `build_app` builds the embedder, the SQLite index, the file skill store and the use cases, exposed on `App`.

## User Stories

1. As a maintainer, I want one `Embedder` contract suite run against `HashingEmbedder` and `OpenAICompatibleEmbedder` (fake transport): one finite vector per text in order, right dimensions, deterministic, empty batch returns `[]` with no call, error translation.
2. As a maintainer, I want one `VectorIndex` contract suite run against `SqliteVectorIndex` covering the port docstring: user scoping, atomic idempotent upsert replace, `get` missing, search order and limit, embedder-identity filtering, dimension mismatch, `list` ordering, idempotent deletes, `count_stale`, blank user and `limit < 1` errors.
3. As a maintainer, I want one `SkillStore` contract suite run against `FileSkillStore`: replace on save, missing get and delete, ordered list, path-escaping names rejected on every method.
4. As a maintainer, I want the harness lists to make a future adapter a one-line addition.
5. As an operator, I want `JUNE_EMBEDDER_PROVIDER` (`hashing` default, or `openai`), `JUNE_EMBEDDER_MODEL`, `JUNE_EMBEDDER_DIMENSIONS`, `JUNE_EMBEDDER_API_KEY` and `JUNE_EMBEDDER_BASE_URL`, with the key and base URL falling back to the LLM ones.
6. As an operator, I want a missing key for the `openai` embedder to stop startup with a one-line `ConfigError`.
7. As an operator, I want the index stored at `<data_dir>/memory.db` and skills at `<data_dir>/skills`, with the data directory created if missing.
8. As the runtime, I want `App` to hold `embedder`, `vector_index`, `skill_store`, `remember_fact`, `remember_episode`, `recall` and `forget`, built once and sharing one clock and id generator.
9. As the runtime, I want the default boot (mock LLM, hashing embedder) to need no network and no key.
10. As an architect, I want only `composition.py` to import memory adapters, and all five import contracts to keep passing.
11. As a maintainer, I want the Phase 2 exit check verified and noted in the PR.

## Implementation Decisions

- Contract files: `tests/contract/test_embedder_contract.py`, `test_vector_index_contract.py`, `test_skill_store_contract.py`, using the same `Harness` + `pytest.param` pattern as `test_chat_model_contract.py`.
- Settings fields on `Settings`: `embedder_provider: Literal["hashing", "openai"]`, `embedder_model`, `embedder_dimensions` (1 to 8192), `embedder_api_key`, `embedder_base_url`; a model validator requires an effective key for `openai`.
- `composition.py` gains `build_embedder(settings)` and `build_memory(settings, embedder)`; `App` gains the fields above.
- `Consolidate` and `RememberConversation` are not wired: no `Summarizer` adapter exists yet (it needs the llm module, a later phase).
- No ADR: follows ADR 0006 (one composition root).

## Testing Decisions

- Contract tests use real adapters, in-memory SQLite and `tmp_path`; the OpenAI embedder uses the fake transport from `tests/openai_fakes.py`.
- Composition tests cover provider selection, key fallback, missing key and the created data files.
- `make check` passes.

## Out of Scope

- A Summarizer adapter, wiring consolidation, scheduling, the runtime loop (Phase 3), new adapters.

## Further Notes

- Linear: SHIP-324.
