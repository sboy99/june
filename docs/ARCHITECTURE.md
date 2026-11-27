# Architecture

## Goals
A modular agent whose boundaries are enforced by tooling, so vendors can change and core logic stays testable.

## Module map
- `memory`: facts, episodes, skills (domain, application, adapters inside)
- `runtime`: the loop, budgets and context builder
- `safety`: classifiers and judges behind ports
- `conversation`: sessions and turns
- `tooling`: the `Tool` port and `ToolRegistry`, the confined file tools `read_file` and `write_file` (Workspace-only; composition passes the protected roots as absolute paths), the SSRF-safe `web_fetch` (httpx lives in `tooling.adapters.web_fetch`; URL and address policy in `tooling.adapters.net_policy`; every hop is validated and the connection goes to the validated address; Risk `medium`; output framed as untrusted), plus sandbox, MCP transport and sub-agent runner ports
- `scheduling`: job store port
- `llm`: chat model port, mock adapter now
- `interfaces`: the CLI
- `observability`, `shared`: logging, errors, ids, clock
- `config.py`: the only reader of environment variables
- `composition.py`: the only place where wiring happens

## Dependency rule and the five contracts
Higher layers import lower ones, never the reverse. Layers, top to bottom: interfaces and scheduling; runtime; conversation, memory, safety, tooling and llm (independent of each other); observability; shared (observability may import shared, never the reverse; see [ADR 0007](adr/0007-observability-above-shared-layer.md)). The contracts in `.importlinter`, run by `make arch`:

1. **Module layers**: the ordering above; same-level modules never import each other.
2. **Inside memory**: adapters over application over domain.
3. **Pure domain**: `memory.domain` imports no pydantic, sqlite3, httpx, anthropic, openai, asyncio or adapters.
4. **Adapters private**: only the composition root and tests import adapters.
5. **Vendor SDKs stay in adapters**: anthropic, openai, httpx, sqlite3 and docker only appear inside adapters.

Same-level modules cannot call each other, so a cross-module need becomes a port that the composition root fills. Known cases: memory consolidation needs a model (`memory.ports.Summarizer`, filled by an llm adapter); safety judges need a model (`safety.ports.Judge`); sub-agent delegation needs the loop (`tooling.ports.SubAgentRunner`, filled by runtime).

## Gate policy

What each safety Gate checks, which Decisions it may return, and what happens when its checker fails (see [ADR 0011](adr/0011-gates-fail-closed.md)). The table is mirrored in code by `june.safety.GATE_POLICIES`.

| Gate | Checks | Decisions | On checker error |
|------|--------|-----------|------------------|
| `input` | user message text | `allow`, `deny` | `deny` |
| `tool` | tool call name and arguments | `allow`, `deny`, `ask` | `deny` |
| `memory_write` | text about to be remembered | `allow`, `deny` | `deny` |
| `end_loop` | final assistant answer | `allow`, `deny` | `allow` |

Gates are wired in `composition.py`: the Input and End-loop gates guard `ChatService`, the Memory-write gate guards memory writes and the Skill store, and `App.tool_runner` is `GatedToolRunner(RegistryToolRunner(ToolRegistry))`, with `ToolGate` rating tools from the registry's Risk levels (see [ADR 0012](adr/0012-tool-definition-and-registry-adapter.md)). The registry starts empty until Phase 5 tools land. A blocked turn ends as `safety_denied`.

Every decision logs `gate`, `decision`, `risk`, `reason` and `subject_digest` (a Content digest, never the raw text). `ask` is treated as `deny` until a confirmation flow exists.

## One request, end to end
1. `june` (CLI) builds `Settings` from `JUNE_*` environment variables.
2. `build_app(settings)` reads the persona file and returns an `App`; a missing or empty file stops startup with a one-line error.
3. The CLI prints `june <version> ready (persona: <n> chars)` and exits 0.
4. From Phase 1, the runtime receives the persona text, runs steps, calls ports (`ChatModel`, memory ports) and returns a reply. Adapters behind those ports are the only code that touches vendors.

## Where to add things
- **Adapter**: add a file under the module's `adapters/`, implement the port, and register it in `composition.py`. For example a Qdrant memory adapter goes in `memory/adapters/qdrant.py`, implements `VectorIndex` and is registered in `composition.py`.
- **Tool**: implement the `tooling.Tool` port and add it to the `ToolRegistry` built in `composition.py`.
- **Module**: create a package with a docstring, `__all__`, `ports.py`, and place it in the layers contract.

## Deliberately not here
Microservices, a DI container, an event bus.
