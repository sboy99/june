"""A fake `Tool` shared by the tooling tests."""

from collections.abc import Mapping
from typing import Any

from june.tooling import RiskLevel, ToolDefinition

SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "count": {"type": "integer"},
        "ratio": {"type": "number"},
        "flag": {"type": "boolean"},
        "items": {"type": "array"},
        "mode": {"type": "string", "enum": ["r", "w"]},
    },
    "required": ["path"],
    "additionalProperties": False,
}


class FakeTool:
    def __init__(
        self,
        name: str = "fake",
        risk: RiskLevel = "low",
        parameters: Mapping[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.definition = ToolDefinition(
            name, "a fake tool", SCHEMA if parameters is None else parameters
        )
        self.risk = risk
        self._error = error
        self.calls: list[Mapping[str, Any]] = []

    async def run(self, arguments: Mapping[str, Any]) -> str:
        self.calls.append(arguments)
        if self._error is not None:
            raise self._error
        return "ok"
