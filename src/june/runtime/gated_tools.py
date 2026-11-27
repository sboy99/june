"""A `ToolRunner` that asks a guard before every call."""

from collections.abc import Sequence

from june.llm import ToolCall, ToolResult, ToolSpec
from june.runtime.ports import ToolGuard, ToolRunner


class GatedToolRunner:
    """Delegates to `inner` only after `guard` passes; a denial raises `SafetyDenied`."""

    def __init__(self, inner: ToolRunner, guard: ToolGuard) -> None:
        self._inner = inner
        self._guard = guard

    @property
    def specs(self) -> Sequence[ToolSpec]:
        return self._inner.specs

    async def run(self, call: ToolCall) -> ToolResult:
        await self._guard.check(call.name, call.arguments)
        return await self._inner.run(call)
