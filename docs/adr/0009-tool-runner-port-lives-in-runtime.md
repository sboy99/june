# ADR 0009: The tool runner port lives in the runtime

- Status: accepted

## Context
The agent loop must run tools the model asks for. `ToolCall`, `ToolResult` and `ToolSpec` belong to `llm`. `tooling` and `llm` are siblings in the layer contract, so a port in `tooling.ports` cannot mention those types.

## Decision
`ToolRunner` is defined in `runtime/ports.py`, next to its only consumer, using `llm` types. The composition root adapts concrete tooling (sandbox, MCP, sub-agents) into a `ToolRunner`. Safety gates wrap a `ToolRunner` and raise `SafetyDenied`; the loop turns that into an error result for the model.

## Consequences
The loop needs no change when tools or gates arrive. The `tooling` stubs (`Sandbox`, `McpTransport`, `SubAgentRunner`) stay vendor-facing and know nothing of the model's message types. The adapter from tooling to `ToolRunner` is extra code in composition.

## Alternatives considered
Moving the tool message types to `shared` (widens the shared layer for one consumer). Letting `tooling` import `llm` (breaks the sibling rule, so every other sibling pair would be next). A generic `Callable` in the loop (loses the documented error contract).
