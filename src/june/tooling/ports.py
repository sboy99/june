"""Ports (interfaces) of the tooling module."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol

# Structurally identical to `safety.ports.RiskLevel`; siblings cannot import each other.
RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ToolDefinition:
    """What a tool is called, what it does, and the JSON schema of its arguments."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


class Tool(Protocol):
    """Port: one capability the model may call.

    Contract every implementation must meet:

    - `definition` describes the tool; `risk` rates its danger.
    - `run` receives arguments already validated against `definition.parameters`
      and returns text for the model.
    - Expected failures raise an `AgentError` subclass (`ToolError`, ...).
    - Error text never contains secrets.
    """

    definition: ToolDefinition
    risk: RiskLevel

    async def run(self, arguments: Mapping[str, Any]) -> str: ...


class Sandbox(Protocol):
    """Port: Sandbox. Stub until the first adapter lands."""


class McpTransport(Protocol):
    """Port: McpTransport. Stub until the first adapter lands."""


class SubAgentRunner(Protocol):
    """Port: SubAgentRunner. Stub until the first adapter lands."""
