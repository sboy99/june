"""Ports of the llm module: vendor-neutral message types and the `ChatModel` port.

Adapters translate vendor formats to and from these types. The runtime sees
only these types. All types are immutable.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Protocol, Self

Role = Literal["system", "user", "assistant", "tool"]
StopReason = Literal["end_turn", "tool_use", "max_tokens"]


def _read_only(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a read-only copy so callers cannot mutate a frozen value through it."""
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True)
class ToolCall:
    """A request from the model to run a tool."""

    id: str
    name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _read_only(self.arguments))


@dataclass(frozen=True)
class ToolResult:
    """The outcome of a tool call, fed back to the model."""

    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call; `parameters` is a JSON schema."""

    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", _read_only(self.parameters))


@dataclass(frozen=True)
class Message:
    """One conversation message.

    `tool_calls` is allowed only on `assistant` messages. `tool_result` is
    present exactly on `tool` messages.
    """

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_result: ToolResult | None = None

    def __post_init__(self) -> None:
        if self.tool_calls and self.role != "assistant":
            raise ValueError("tool_calls are only allowed on assistant messages")
        if (self.role == "tool") != (self.tool_result is not None):
            raise ValueError("tool_result must be present exactly on tool messages")

    @classmethod
    def system(cls, content: str) -> Self:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Self:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str = "", *, tool_calls: tuple[ToolCall, ...] = ()) -> Self:
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, result: ToolResult) -> Self:
        return cls(role="tool", content=result.content, tool_result=result)


@dataclass(frozen=True)
class Usage:
    """Token counts for one model call."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token counts must be non-negative")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ChatResponse:
    """What a `ChatModel` returns.

    Invariants: `message` has role `assistant`; `stop_reason` is `tool_use`
    exactly when the message has tool calls; tool call ids are unique.
    """

    message: Message
    stop_reason: StopReason
    usage: Usage
    model: str

    def __post_init__(self) -> None:
        if self.message.role != "assistant":
            raise ValueError("response message must have role assistant")
        if (self.stop_reason == "tool_use") != bool(self.message.tool_calls):
            raise ValueError("stop_reason is tool_use exactly when the message has tool calls")
        ids = [call.id for call in self.message.tool_calls]
        if len(ids) != len(set(ids)):
            raise ValueError("tool call ids must be unique within a response")


class ChatModel(Protocol):
    """Port: a chat model that turns a conversation into one assistant reply.

    Contract every adapter must meet:

    - `messages` must contain at least one message; otherwise raise
      `PermanentAdapterError`.
    - Return a `ChatResponse` (its invariants are enforced on construction).
    - Retry transient failures internally, up to the configured retry count,
      then raise.
    - Only `TransientAdapterError` (timeout, rate limit, 5xx; retryable) and
      `PermanentAdapterError` (bad credentials, invalid request; not
      retryable) may escape. Vendor exceptions never do.
    - Error messages and logs never contain API keys.
    """

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int | None = None,
    ) -> ChatResponse: ...
