"""The agent loop: ask the model, run requested tools, feed results back, stop.

Every ending has a named `LoopStop`. Errors are caught here and either retried
(retryable model failures), returned to the model as an error tool result
(tool failures), or ended with a stop reason (everything else).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from june.llm import ChatModel, ChatResponse, Message, ToolCall, ToolResult, Usage
from june.observability import get_logger
from june.observability.redaction import redact_text
from june.runtime.ports import ToolRunner
from june.shared import AgentError, DomainError

DEFAULT_MAX_STEPS = 10
DEFAULT_MAX_MODEL_RETRIES = 2
UNEXPECTED_TOOL_FAILURE = "tool failed unexpectedly"

_log = get_logger(__name__)


class LoopStop(StrEnum):
    """Why the loop ended."""

    ANSWERED = "answered"
    MAX_STEPS = "max_steps"
    TOKEN_BUDGET = "token_budget"
    TRUNCATED = "truncated"
    MODEL_ERROR = "model_error"


@dataclass(frozen=True, slots=True)
class Budget:
    """Limits for one turn: model calls and, optionally, total tokens."""

    max_steps: int = DEFAULT_MAX_STEPS
    max_total_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise DomainError("max_steps must be at least 1")
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise DomainError("max_total_tokens must be at least 1")


@dataclass(frozen=True, slots=True)
class LoopResult:
    """The outcome of one run. `reply` is empty unless answered or truncated."""

    stop: LoopStop
    reply: str
    added: tuple[Message, ...]
    steps: int
    usage: Usage
    error_code: str | None = None


def _error_result(call: ToolCall, text: str) -> ToolResult:
    return ToolResult(call.id, redact_text(text), is_error=True)


def _sum_usage(total: Usage, extra: Usage) -> Usage:
    return Usage(total.input_tokens + extra.input_tokens, total.output_tokens + extra.output_tokens)


class AgentLoop:
    """Drives a model and a tool runner until an answer or a budget limit."""

    def __init__(
        self,
        model: ChatModel,
        tools: ToolRunner | None = None,
        budget: Budget | None = None,
        max_model_retries: int = DEFAULT_MAX_MODEL_RETRIES,
    ) -> None:
        if max_model_retries < 0:
            raise DomainError("max_model_retries must not be negative")
        self._model = model
        self._tools = tools
        self._budget = budget or Budget()
        self._max_model_retries = max_model_retries

    async def run(self, messages: Sequence[Message]) -> LoopResult:
        if not messages:
            raise DomainError("messages must not be empty")
        conversation = list(messages)
        added: list[Message] = []
        usage = Usage(0, 0)
        for step in range(1, self._budget.max_steps + 1):
            limit = self._budget.max_total_tokens
            if limit is not None and usage.total_tokens >= limit:
                return self._result(LoopStop.TOKEN_BUDGET, added, step - 1, usage)
            try:
                response = await self._complete(conversation)
            except AgentError as exc:
                _log.warning("model call failed: %s", exc.code)
                return self._result(LoopStop.MODEL_ERROR, added, step, usage, exc.code)
            usage = _sum_usage(usage, response.usage)
            conversation.append(response.message)
            added.append(response.message)
            if response.stop_reason != "tool_use":
                stop = (
                    LoopStop.ANSWERED if response.stop_reason == "end_turn" else LoopStop.TRUNCATED
                )
                return self._result(stop, added, step, usage, reply=response.message.content)
            for tool_message in await self._run_tools(response.message.tool_calls):
                conversation.append(tool_message)
                added.append(tool_message)
        return self._result(LoopStop.MAX_STEPS, added, self._budget.max_steps, usage)

    def _result(
        self,
        stop: LoopStop,
        added: Sequence[Message],
        steps: int,
        usage: Usage,
        error_code: str | None = None,
        reply: str = "",
    ) -> LoopResult:
        return LoopResult(stop, reply, tuple(added), steps, usage, error_code)

    async def _complete(self, conversation: Sequence[Message]) -> ChatResponse:
        specs = tuple(self._tools.specs) if self._tools else ()
        attempt = 0
        while True:
            try:
                return await self._model.complete(conversation, tools=specs)
            except AgentError as exc:
                if not exc.retryable or attempt >= self._max_model_retries:
                    raise
                attempt += 1
                _log.warning("retrying model call (%d): %s", attempt, exc.code)

    async def _run_tools(self, calls: Sequence[ToolCall]) -> list[Message]:
        return [Message.tool(await self._run_tool(call)) for call in calls]

    async def _run_tool(self, call: ToolCall) -> ToolResult:
        known = {spec.name for spec in self._tools.specs} if self._tools else set()
        if self._tools is None or call.name not in known:
            return _error_result(call, f"unknown tool: {call.name}")
        try:
            return await self._tools.run(call)
        except AgentError as exc:
            _log.warning("tool %s failed: %s", call.name, exc.code)
            return _error_result(call, f"{exc.code}: {exc}")
        except Exception:
            _log.exception("tool %s raised an unexpected exception", call.name)
            return _error_result(call, UNEXPECTED_TOOL_FAILURE)
