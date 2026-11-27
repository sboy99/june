"""The tool registry: holds tools by name and validates arguments before running one."""

from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

from june.observability import get_logger
from june.shared.errors import AgentError, ToolError
from june.tooling.ports import RiskLevel, Tool, ToolDefinition
from june.tooling.validation import validate_arguments

_log = get_logger(__name__)


class ToolRegistry:
    """Looks tools up by name; rejects duplicate and blank names at construction."""

    def __init__(self, tools: Iterable[Tool]) -> None:
        by_name: dict[str, Tool] = {}
        for tool in tools:
            name = tool.definition.name
            if not name.strip():
                raise ValueError("tool name is blank")
            if name in by_name:
                raise ValueError(f"duplicate tool name: {name}")
            by_name[name] = tool
        self._tools: Mapping[str, Tool] = MappingProxyType(by_name)

    @property
    def definitions(self) -> Sequence[ToolDefinition]:
        return tuple(tool.definition for tool in self._tools.values())

    @property
    def risks(self) -> Mapping[str, RiskLevel]:
        return MappingProxyType({name: tool.risk for name, tool in self._tools.items()})

    async def run(self, name: str, arguments: Mapping[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool: {name}")
        validate_arguments(tool.definition.parameters, arguments)
        try:
            return await tool.run(arguments)
        except AgentError:
            raise
        except Exception as exc:
            _log.warning("tool %s failed", name, exc_info=True)
            raise ToolError(f"tool {name} failed") from exc
