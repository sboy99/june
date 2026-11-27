# Tool contract and registry (SHIP-338, P5.1)

Status: ready-for-agent
Source: Linear SHIP-338, milestone "Phase 5: Tooling"
Branch: `contactsagarbera/ship-338-p51-tool-contract-and-registry` (from `main`)

## Problem Statement

`ToolRunner` exists as a runtime port, but no tool exists. There is nothing to describe a tool, rate its risk, validate the model's arguments, or look a tool up by name. Phase 5 tools (files, web, terminal, MCP, sub-agents) all need one shared shape.

## Solution

`june.tooling` gains a `Tool` port (spec, Risk level, async run), a `ToolRegistry` that holds tools by name and validates arguments before running one, and a `RegistryToolRunner` that adapts the registry into the runtime `ToolRunner`. The composition root wraps it with `GatedToolRunner`, so every call passes through the Tool gate, and feeds the registry's Risk levels to `ToolGate`.

## User Stories

1. As a tool author, I want one `Tool` port with a spec, a Risk level and an async `run`, so every tool has the same shape.
2. As an operator, I want to register tools by name, so the model is offered a known set.
3. As an operator, I want registering two tools with the same name to fail, so one never shadows another.
4. As the model, I want the registry to list each tool's spec, so I know what I may call.
5. As the runtime, I want an unknown tool name to raise `ToolError`, so the loop returns an error result to the model.
6. As the runtime, I want arguments checked against the tool's JSON schema (required keys, basic types, enum, no unknown keys when `additionalProperties` is false) before `run`, so a tool never sees malformed input.
7. As the runtime, I want invalid arguments to raise `ToolError` naming the offending field, never the value, so error text leaks nothing.
8. As the runtime, I want a tool that raises an unexpected exception to surface as `ToolError` with a generic message, so the loop never crashes.
9. As the runtime, I want `ToolError` and other `AgentError`s raised by a tool to pass through unchanged.
10. As an operator, I want the registry to expose a name-to-Risk-level table, so `ToolGate` rates real tools.
11. As an operator, I want every call to run through gate 2, so the wired runner is `GatedToolRunner(RegistryToolRunner)`.

## Implementation Decisions

- `tooling/ports.py`: `Tool` Protocol: `definition: ToolDefinition`, `risk: RiskLevel`, `async run(arguments: Mapping[str, Any]) -> str`. `tooling` cannot import `safety` or `llm` (siblings), so `RiskLevel` is a local `Literal["low", "medium", "high"]` (structurally identical to `safety.ports.RiskLevel`) and `ToolDefinition(name, description, parameters)` is a tooling-owned frozen dataclass.
- Tools return text; the runner builds the `ToolResult` (`call_id` from the call).
- `RegistryToolRunner` lives in `june/tool_runner.py`, a top-level wiring module that may import both `tooling` and `llm`, per ADR 0009 ("the composition root adapts concrete tooling into a ToolRunner"). It maps `ToolDefinition` to `ToolSpec` and a tool's text to a `ToolResult`.
- `tooling/registry.py`: `ToolRegistry(tools)` (rejects duplicates and blank names, copies the input), `definitions`, `risks`, `async run(name, arguments) -> str`.
- `tooling/validation.py`: small JSON-schema subset validator (`type`, `required`, `properties`, `enum`, `additionalProperties`), no new dependency.
- New ADR 0012 records the ToolDefinition/adapter split and the in-house validator.
- Glossary: add **Tool** and **Tool registry** [tooling].
- The registry starts empty in composition (no real tools yet); wiring still happens so later issues only add tools.

## Testing Decisions

- Through `ToolRegistry.run` and `RegistryToolRunner.run` with fake tools; one wiring test via `build_app`.
- Prior art: `tests/unit/test_safety_tool_gate.py`, `tests/unit/test_runtime_loop.py`.
- `make check` passes; `june.tooling` coverage at least 80%.

## Out of Scope

Real tools (SHIP-339 onward), sandboxing, approval UI.

## Further Notes

Linear: SHIP-338.
