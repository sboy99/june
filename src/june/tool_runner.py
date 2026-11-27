"""Wiring: adapts the tool registry into the runtime `ToolRunner` (see ADR 0012)."""

from collections.abc import Sequence

from june.llm import ToolCall, ToolResult, ToolSpec
from june.tooling import ToolRegistry


class RegistryToolRunner:
    """A `ToolRunner` backed by a `ToolRegistry`."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @property
    def specs(self) -> Sequence[ToolSpec]:
        return tuple(
            ToolSpec(d.name, d.description, d.parameters) for d in self._registry.definitions
        )

    async def run(self, call: ToolCall) -> ToolResult:
        content = await self._registry.run(call.name, call.arguments)
        return ToolResult(call_id=call.id, content=content)
