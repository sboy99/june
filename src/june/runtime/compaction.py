"""Compaction: shrink the oldest tool output when the conversation nears its size limit.

Pure and conservative: only tool result text is replaced, and the call id and
error flag stay, so every tool call keeps its answer and the model still sees
that the call happened. Characters stand in for tokens, as in the context builder.
"""

from collections.abc import Sequence
from dataclasses import replace

from june.llm import Message
from june.shared import DomainError

DEFAULT_MAX_CHARS = 48_000
DEFAULT_KEEP_RECENT = 4
COMPACTED_PLACEHOLDER = "[tool output compacted]"


def _size(messages: Sequence[Message]) -> int:
    return sum(len(message.content) for message in messages)


def _compacted(message: Message) -> Message:
    result = message.tool_result
    assert result is not None
    return Message.tool(replace(result, content=COMPACTED_PLACEHOLDER))


class Compactor:
    """Replaces the oldest tool results with a placeholder until the size limit is met."""

    def __init__(
        self, max_chars: int = DEFAULT_MAX_CHARS, keep_recent: int = DEFAULT_KEEP_RECENT
    ) -> None:
        if max_chars < 1:
            raise DomainError("max_chars must be at least 1")
        if keep_recent < 0:
            raise DomainError("keep_recent must not be negative")
        self._max_chars = max_chars
        self._keep_recent = keep_recent

    def compact(self, messages: Sequence[Message]) -> tuple[Message, ...]:
        result = list(messages)
        size = _size(result)
        protected_from = max(0, len(result) - self._keep_recent)
        for index in range(protected_from):
            if size <= self._max_chars:
                break
            message = result[index]
            if message.role != "tool" or message.content == COMPACTED_PLACEHOLDER:
                continue
            shrunk = _compacted(message)
            size -= len(message.content) - len(shrunk.content)
            result[index] = shrunk
        return tuple(result)
