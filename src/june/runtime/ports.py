"""Ports (interfaces) of the runtime module."""

from collections.abc import Sequence
from typing import Protocol

from june.llm import ToolCall, ToolResult, ToolSpec


class ToolRunner(Protocol):
    """Port: runs the tools the model may call.

    Contract every implementation must meet:

    - `specs` lists the tools offered to the model.
    - `run` executes one call and returns its `ToolResult`.
    - Expected failures raise an `AgentError` subclass (`ToolError`,
      `SafetyDenied`, ...); the loop turns them into error results for the model.
    - Error text never contains secrets.
    """

    @property
    def specs(self) -> Sequence[ToolSpec]: ...

    async def run(self, call: ToolCall) -> ToolResult: ...
