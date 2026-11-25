"""Ports (interfaces) of the tooling module."""

from typing import Protocol


class Sandbox(Protocol):
    """Port: Sandbox. Stub until the first adapter lands."""


class McpTransport(Protocol):
    """Port: McpTransport. Stub until the first adapter lands."""


class SubAgentRunner(Protocol):
    """Port: SubAgentRunner. Stub until the first adapter lands."""
