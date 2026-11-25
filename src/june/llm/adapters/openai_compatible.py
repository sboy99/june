"""`ChatModel` adapter for any OpenAI-compatible chat-completions endpoint."""

import json
from collections.abc import Sequence
from typing import Any

import httpx2
import openai
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCallUnion

from june.llm.ports import ChatResponse, Message, StopReason, ToolCall, ToolSpec, Usage
from june.shared import AdapterError, PermanentAdapterError, TransientAdapterError

_TRANSIENT_STATUSES = frozenset({408, 409, 429})
_SERVER_ERROR_FLOOR = 500
_FINISH_TO_STOP: dict[str, StopReason] = {"stop": "end_turn", "length": "max_tokens"}


def _wire_message(message: Message) -> dict[str, Any]:
    if message.role == "tool" and message.tool_result is not None:
        return {
            "role": "tool",
            "tool_call_id": message.tool_result.call_id,
            "content": message.tool_result.content,
        }
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(dict(call.arguments))},
            }
            for call in message.tool_calls
        ]
    return wire


def _wire_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.parameters),
        },
    }


def _parse_arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise PermanentAdapterError(
            "model returned tool arguments that are not valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise PermanentAdapterError("model returned tool arguments that are not a JSON object")
    return parsed


def _translate_error(exc: openai.OpenAIError) -> AdapterError:
    """Map an SDK exception to a june adapter error; never echo bodies or keys."""
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        text = f"openai request failed: {type(exc).__name__} (status {status})"
        if status in _TRANSIENT_STATUSES or status >= _SERVER_ERROR_FLOOR:
            return TransientAdapterError(text, cause=exc)
        return PermanentAdapterError(text, cause=exc)
    text = f"openai request failed: {type(exc).__name__}"
    if isinstance(exc, openai.APIConnectionError):
        return TransientAdapterError(text, cause=exc)
    return PermanentAdapterError(text, cause=exc)


class OpenAICompatibleChatModel:
    """Talks to an OpenAI-compatible server; retries are the SDK's, bounded by `max_retries`."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=http_client,
        )

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int | None = None,
    ) -> ChatResponse:
        if not messages:
            raise PermanentAdapterError("messages must not be empty")
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [_wire_message(m) for m in messages],
        }
        if tools:
            request["tools"] = [_wire_tool(t) for t in tools]
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        try:
            completion = await self._client.chat.completions.create(**request)
        except openai.OpenAIError as exc:
            raise _translate_error(exc) from exc
        return self._to_response(completion)

    def _to_response(self, completion: ChatCompletion) -> ChatResponse:
        if not completion.choices:
            raise PermanentAdapterError("model returned no choices")
        choice = completion.choices[0]
        tool_calls = tuple(self._to_tool_call(call) for call in choice.message.tool_calls or ())
        stop_reason = self._stop_reason(choice.finish_reason, bool(tool_calls))
        usage = completion.usage
        return ChatResponse(
            message=Message.assistant(choice.message.content or "", tool_calls=tool_calls),
            stop_reason=stop_reason,
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            model=completion.model or self._model,
        )

    @staticmethod
    def _to_tool_call(call: ChatCompletionMessageToolCallUnion) -> ToolCall:
        if call.type != "function":
            raise PermanentAdapterError(f"unsupported tool call type: {call.type}")
        return ToolCall(
            id=call.id,
            name=call.function.name,
            arguments=_parse_arguments(call.function.arguments),
        )

    @staticmethod
    def _stop_reason(finish_reason: str | None, has_tool_calls: bool) -> StopReason:
        if has_tool_calls:
            return "tool_use"
        if finish_reason == "tool_calls":
            raise PermanentAdapterError("model reported tool_calls but returned none")
        stop = _FINISH_TO_STOP.get(finish_reason or "")
        if stop is None:
            raise PermanentAdapterError(f"unsupported finish reason: {finish_reason}")
        return stop
