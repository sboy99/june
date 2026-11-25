from collections.abc import Sequence
from dataclasses import FrozenInstanceError

import pytest

from june import llm
from june.llm import (
    ChatModel,
    ChatResponse,
    Message,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)

pytestmark = pytest.mark.unit


def test_convenience_constructors_set_roles():
    assert Message.system("s").role == "system"
    assert Message.user("u").role == "user"
    assert Message.assistant("a").role == "assistant"


def test_assistant_message_carries_tool_calls():
    call = ToolCall(id="c1", name="search", arguments={"q": "june"})

    message = Message.assistant(tool_calls=(call,))

    assert message.tool_calls == (call,)
    assert message.content == ""


def test_tool_message_carries_result():
    message = Message.tool(ToolResult(call_id="c1", content="42"))

    assert message.role == "tool"
    assert message.tool_result is not None
    assert message.tool_result.is_error is False


def test_tool_calls_on_a_user_message_are_rejected():
    call = ToolCall(id="c1", name="search", arguments={})

    with pytest.raises(ValueError, match="tool_calls"):
        Message(role="user", content="hi", tool_calls=(call,))


def test_tool_message_without_result_is_rejected():
    with pytest.raises(ValueError, match="tool_result"):
        Message(role="tool", content="x")


def test_tool_result_on_a_non_tool_message_is_rejected():
    with pytest.raises(ValueError, match="tool_result"):
        Message(role="user", content="x", tool_result=ToolResult(call_id="c", content="x"))


def test_messages_are_frozen():
    message = Message.user("hi")

    with pytest.raises(FrozenInstanceError):
        message.content = "changed"  # type: ignore[misc]


def test_tool_call_arguments_are_read_only_and_copied():
    source = {"q": "june"}
    call = ToolCall(id="c1", name="search", arguments=source)

    source["q"] = "mutated"

    assert call.arguments["q"] == "june"
    with pytest.raises(TypeError):
        call.arguments["q"] = "x"  # type: ignore[index]


def test_tool_spec_parameters_are_read_only():
    spec = ToolSpec(name="search", description="d", parameters={"type": "object"})

    with pytest.raises(TypeError):
        spec.parameters["type"] = "x"  # type: ignore[index]


def test_usage_total_is_input_plus_output():
    assert Usage(input_tokens=3, output_tokens=4).total_tokens == 7


@pytest.mark.parametrize(
    "kwargs", [{"input_tokens": -1, "output_tokens": 0}, {"input_tokens": 0, "output_tokens": -1}]
)
def test_negative_usage_is_rejected(kwargs):
    with pytest.raises(ValueError, match="non-negative"):
        Usage(**kwargs)


def test_response_requires_an_assistant_message():
    with pytest.raises(ValueError, match="assistant"):
        ChatResponse(
            message=Message.user("hi"),
            stop_reason="end_turn",
            usage=Usage(input_tokens=1, output_tokens=1),
            model="m",
        )


def test_tool_use_stop_reason_requires_tool_calls_and_vice_versa():
    usage = Usage(input_tokens=1, output_tokens=1)
    call = ToolCall(id="c1", name="t", arguments={})

    with pytest.raises(ValueError, match="tool_use"):
        ChatResponse(message=Message.assistant("x"), stop_reason="tool_use", usage=usage, model="m")
    with pytest.raises(ValueError, match="tool_use"):
        ChatResponse(
            message=Message.assistant(tool_calls=(call,)),
            stop_reason="end_turn",
            usage=usage,
            model="m",
        )


def test_duplicate_tool_call_ids_in_a_response_are_rejected():
    usage = Usage(input_tokens=1, output_tokens=1)
    calls = (ToolCall(id="c1", name="a", arguments={}), ToolCall(id="c1", name="b", arguments={}))

    with pytest.raises(ValueError, match="unique"):
        ChatResponse(
            message=Message.assistant(tool_calls=calls),
            stop_reason="tool_use",
            usage=usage,
            model="m",
        )


class EchoModel:
    """Satisfies ChatModel structurally, without inheriting from it."""

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[ToolSpec] = (),
        max_tokens: int | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            message=Message.assistant(messages[-1].content),
            stop_reason="end_turn",
            usage=Usage(input_tokens=1, output_tokens=1),
            model="echo",
        )


async def test_a_plain_class_satisfies_the_chat_model_port():
    model: ChatModel = EchoModel()

    response = await model.complete([Message.user("hello")])

    assert response.message.content == "hello"


def test_llm_package_exports_the_port_vocabulary():
    expected = {
        "ChatModel",
        "ChatResponse",
        "Message",
        "Role",
        "StopReason",
        "ToolCall",
        "ToolResult",
        "ToolSpec",
        "Usage",
    }

    assert expected <= set(llm.__all__)
