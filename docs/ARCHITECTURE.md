# Architecture

## Goals
A modular agent whose boundaries are enforced by tooling, so vendors can change and core logic stays testable.

## Module map
- `memory`: facts, episodes, skills (domain, application, adapters inside)
- `runtime`: the loop, budgets and context builder
- `safety`: classifiers and judges behind ports
- `conversation`: sessions and turns
- `tooling`: sandbox, MCP transport and sub-agent runner ports
- `scheduling`: job store port
- `llm`: chat model port, mock adapter now
- `interfaces`: the CLI
- `observability`, `shared`: logging, errors, ids, clock
- `config.py`: the only reader of environment variables
- `composition.py`: the only place where wiring happens

## Dependency rule and the five contracts
Higher layers import lower ones, never the reverse. Layers, top to bottom: interfaces and scheduling; runtime; conversation, memory, safety, tooling and llm (independent of each other); observability and shared. The contracts in `.importlinter`, run by `make arch`:

1. **Module layers**: the ordering above; same-level modules never import each other.
2. **Inside memory**: adapters over application over domain.
3. **Pure domain**: `memory.domain` imports no pydantic, sqlite3, httpx, anthropic, openai, asyncio or adapters.
4. **Adapters private**: only the composition root and tests import adapters.
5. **Vendor SDKs stay in adapters**: anthropic, openai, httpx, sqlite3 and docker only appear inside adapters.

Same-level modules cannot call each other, so a cross-module need becomes a port that the composition root fills. Known cases: memory consolidation needs a model (`memory.ports.Summarizer`, filled by an llm adapter); safety judges need a model (`safety.ports.Judge`); sub-agent delegation needs the loop (`tooling.ports.SubAgentRunner`, filled by runtime).

## One request, end to end
1. `june` (CLI) builds `Settings` from `JUNE_*` environment variables.
2. `build_app(settings)` reads the persona file and returns an `App`; a missing or empty file stops startup with a one-line error.
3. The CLI prints `june <version> ready (persona: <n> chars)` and exits 0.
4. From Phase 1, the runtime receives the persona text, runs steps, calls ports (`ChatModel`, memory ports) and returns a reply. Adapters behind those ports are the only code that touches vendors.

## Where to add things
- **Adapter**: add a file under the module's `adapters/`, implement the port, and register it in `composition.py`. For example a Qdrant memory adapter goes in `memory/adapters/qdrant.py`, implements `VectorIndex` and is registered in `composition.py`.
- **Tool**: implement it behind the `tooling` ports and wire it in `composition.py`.
- **Module**: create a package with a docstring, `__all__`, `ports.py`, and place it in the layers contract.

## Deliberately not here
Microservices, a DI container, an event bus.
