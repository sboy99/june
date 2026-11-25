"""Deterministic scripted `ChatModel` for tests and offline runs."""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from june.llm.ports import ChatResponse, Message, ToolSpec, Usage
from june.shared import AgentError, PermanentAdapterError

ScriptStep = str | ChatResponse | AgentError


@dataclass(frozen=True)
class MockCall:
    """One recorded call to the mock."""

    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...]
    max_tokens: int | None


def _word_count(messages: Sequence[Message]) -> int:
    return sum(len(message.content.split()) for message in messages)


class MockChatModel:
    """Replays a script of steps in order, or echoes the last user message.

    With no script it runs in echo mode. Every call is recorded in `calls`.
    """

    def __init__(self, script: Iterable[ScriptStep] | None = None, *, model: str = "mock") -> None:
        self._steps: Iterator[ScriptStep] | None = None if script is None else iter(script)
        self._model = model
        self._calls: list[MockCall] = []

    @property
    def calls(self) -> tuple[MockCall, ...]:
        return tuple(self._calls)

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int | None = None,
    ) -> ChatResponse:
        if not messages:
            raise PermanentAdapterError("messages must not be empty")
        self._calls.append(MockCall(tuple(messages), tuple(tools), max_tokens))
        if self._steps is None:
            return self._reply(self._echo(messages), messages)
        step = next(self._steps, None)
        if step is None:
            raise PermanentAdapterError("mock script exhausted")
        if isinstance(step, AgentError):
            raise step
        if isinstance(step, str):
            return self._reply(step, messages)
        return step

    def _echo(self, messages: Sequence[Message]) -> str:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return f"echo: {last_user}"

    def _reply(self, text: str, messages: Sequence[Message]) -> ChatResponse:
        return ChatResponse(
            message=Message.assistant(text),
            stop_reason="end_turn",
            usage=Usage(input_tokens=_word_count(messages), output_tokens=len(text.split())),
            model=self._model,
        )
