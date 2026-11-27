# ADR 0012: Tool definition and registry adapter

- Status: accepted

## Context
Phase 5 tools (files, web, terminal, MCP, sub-agents) need one shared shape: a spec, a Risk level and an async run. `tooling`, `llm` and `safety` are siblings in the layer contract, so `tooling` can use neither `llm.ToolSpec` nor `safety.RiskLevel`. [ADR 0009](0009-tool-runner-port-lives-in-runtime.md) already says the composition root adapts concrete tooling into a `ToolRunner`.

## Decision
`tooling.ports` owns a frozen `ToolDefinition(name, description, parameters)` and a local `RiskLevel` literal, structurally identical to `safety.ports.RiskLevel`. A `Tool` returns text. `ToolRegistry` holds tools by name, rejects duplicate and blank names, validates arguments, and turns unexpected exceptions into a generic `ToolError`; `AgentError`s pass through unchanged. `RegistryToolRunner` in the top-level wiring module `june/tool_runner.py` maps `ToolDefinition` to `ToolSpec` and a tool's text to a `ToolResult`. The composition root wraps it with `GatedToolRunner` and feeds `ToolRegistry.risks` to `ToolGate`.

Arguments are validated by a small in-house JSON-schema subset (`type`, `required`, `properties`, `enum`, `additionalProperties`). Errors name the field, never the value.

## Consequences
Tools know nothing of the model's message types, and every call passes Gate 2. Later issues only add tools to the registry. The `RiskLevel` literal is duplicated; a drift would be caught by mypy at the composition root. The validator covers only the subset, so tools needing more (nested schemas, formats) must extend it.

## Alternatives considered
The `jsonschema` library (a new dependency for a handful of checks). Letting `tooling` import `llm` (breaks the sibling rule). Putting the adapter inside `composition.py` (grows the root; a separate module is testable alone).
