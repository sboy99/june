"""Shared error hierarchy rooted at `AgentError`.

Every expected failure carries a stable machine-readable `code`, a human
message and a `retryable` flag. Codes are part of the contract and must not
change once released.
"""

from typing import ClassVar


class AgentError(Exception):
    """Base class for expected, user-facing failures."""

    code: ClassVar[str] = "agent_error"
    default_retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        retryable: bool | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable: bool = self.default_retryable if retryable is None else retryable
        if cause is not None:
            self.__cause__ = cause


class ConfigError(AgentError):
    """Configuration is missing or invalid."""

    code = "config_error"


class PersonaNotFound(AgentError):
    """Persona file is missing, unreadable or empty."""

    code = "persona_not_found"


class DomainError(AgentError):
    """A business rule was violated."""

    code = "domain_error"


class AdapterError(AgentError):
    """An adapter failed talking to a vendor, database or file system."""

    code = "adapter_error"


class TransientAdapterError(AdapterError):
    """Adapter failure that may succeed on retry (timeout, rate limit)."""

    code = "adapter_transient"
    default_retryable = True


class PermanentAdapterError(AdapterError):
    """Adapter failure that will not succeed on retry (bad credentials)."""

    code = "adapter_permanent"


class SafetyDenied(AgentError):
    """A safety gate blocked the action. Never retried."""

    code = "safety_denied"


class BudgetExceeded(AgentError):
    """Steps, tokens or time budget for a turn was exceeded. Never retried."""

    code = "budget_exceeded"


class ToolError(AgentError):
    """A tool call failed in an expected way."""

    code = "tool_error"
