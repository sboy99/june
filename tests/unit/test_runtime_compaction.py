import pytest

from june.llm import Message, ToolCall, ToolResult
from june.runtime import COMPACTED_PLACEHOLDER, Compactor
from june.shared import DomainError

pytestmark = pytest.mark.unit


def tool_pair(call_id: str, output: str) -> tuple[Message, Message]:
    call = ToolCall(call_id, "echo", {})
    return Message.assistant("", tool_calls=(call,)), Message.tool(ToolResult(call_id, output))


def conversation(*outputs: str) -> list[Message]:
    messages = [Message.system("persona"), Message.user("go")]
    for number, output in enumerate(outputs):
        messages.extend(tool_pair(f"c{number}", output))
    return messages


def test_conversation_under_the_limit_is_returned_unchanged():
    messages = conversation("small")

    result = Compactor(max_chars=1000, keep_recent=2).compact(messages)

    assert result == tuple(messages)


def test_oldest_tool_results_are_compacted_first_until_under_the_limit():
    messages = conversation("a" * 500, "b" * 500, "c" * 500)

    result = Compactor(max_chars=1200, keep_recent=2).compact(messages)

    tool_contents = [m.content for m in result if m.role == "tool"]
    assert tool_contents == [COMPACTED_PLACEHOLDER, "b" * 500, "c" * 500]


def test_compacted_result_keeps_its_call_id_and_error_flag():
    call = ToolCall("c0", "echo", {})
    messages = [
        Message.system("p"),
        Message.assistant("", tool_calls=(call,)),
        Message.tool(ToolResult("c0", "x" * 500, is_error=True)),
        Message.user("again"),
    ]

    result = Compactor(max_chars=100, keep_recent=1).compact(messages)

    assert result[2].tool_result == ToolResult("c0", COMPACTED_PLACEHOLDER, is_error=True)
    assert result[2].content == COMPACTED_PLACEHOLDER


def test_recent_messages_and_non_tool_messages_are_never_compacted():
    messages = conversation("a" * 500, "b" * 500)

    result = Compactor(max_chars=10, keep_recent=2).compact(messages)

    assert result[:2] == tuple(messages[:2])
    assert [m.role for m in result] == [m.role for m in messages]
    assert result[-2:] == tuple(messages[-2:])


def test_input_messages_are_not_mutated():
    messages = conversation("a" * 500, "b" * 500)
    before = list(messages)

    Compactor(max_chars=10, keep_recent=1).compact(messages)

    assert messages == before


@pytest.mark.parametrize("kwargs", [{"max_chars": 0}, {"keep_recent": -1}])
def test_invalid_limits_are_rejected(kwargs):
    with pytest.raises(DomainError):
        Compactor(**kwargs)
