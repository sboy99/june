"""Shared: small cross-cutting primitives (errors, ids, clock)."""

from june.shared.clock import Clock, FixedClock, SystemClock
from june.shared.errors import (
    AdapterError,
    AgentError,
    BudgetExceeded,
    ConfigError,
    DomainError,
    PermanentAdapterError,
    PersonaNotFound,
    SafetyDenied,
    ToolError,
    TransientAdapterError,
)
from june.shared.ids import IdGenerator, UuidGenerator, new_id

__all__ = [
    "AdapterError",
    "AgentError",
    "BudgetExceeded",
    "Clock",
    "ConfigError",
    "DomainError",
    "FixedClock",
    "IdGenerator",
    "PermanentAdapterError",
    "PersonaNotFound",
    "SafetyDenied",
    "SystemClock",
    "ToolError",
    "TransientAdapterError",
    "UuidGenerator",
    "new_id",
]
