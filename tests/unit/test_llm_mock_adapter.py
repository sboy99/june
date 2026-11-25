import pytest

from june.llm import ChatModel, ChatResponse, Message, ToolCall, ToolSpec, Usage
from june.llm.adapters.mock import MockChatModel
from june.shared import PermanentAdapterError, TransientAdapterError

pytestmark = pytest.mark.unit

HELLO = [Message.user("hello there")]


async def test_scripted_replies_come_back_in_order():
    model: ChatModel = MockChatModel(["one", "two"])

    first = await model.complete(HELLO)
    second = await model.complete(HELLO)

    assert [first.message.content, second.message.content] == ["one", "two"]
    assert first.stop_reason == "end_turn"
    assert first.message.role == "assistant"


async def test_string_step_usage_is_derived_from_word_counts():
    model = MockChatModel(["a b c"])

    response = await model.complete([Message.user("x y")])

    assert response.usage == Usage(input_tokens=2, output_tokens=3)


async def test_full_response_step_is_returned_unchanged():
    call = ToolCall(id="c1", name="search", arguments={"q": "x"})
    scripted = ChatResponse(
        message=Message.assistant(tool_calls=(call,)),
        stop_reason="tool_use",
        usage=Usage(input_tokens=1, output_tokens=1),
        model="scripted",
    )
    model = MockChatModel([scripted])

    assert await model.complete(HELLO) == scripted


async def test_error_step_is_raised():
    model = MockChatModel([TransientAdapterError("rate limited"), "ok"])

    with pytest.raises(TransientAdapterError):
        await model.complete(HELLO)
    assert (await model.complete(HELLO)).message.content == "ok"


async def test_exhausted_script_raises_permanent_error():
    model = MockChatModel(["only"])
    await model.complete(HELLO)

    with pytest.raises(PermanentAdapterError, match="exhausted"):
        await model.complete(HELLO)


async def test_empty_messages_are_rejected_without_consuming_a_step():
    model = MockChatModel(["kept"])

    with pytest.raises(PermanentAdapterError):
        await model.complete([])

    assert (await model.complete(HELLO)).message.content == "kept"


async def test_calls_are_recorded():
    model = MockChatModel(["a"])
    spec = ToolSpec(name="t", description="d")

    await model.complete(HELLO, tools=[spec], max_tokens=50)

    (call,) = model.calls
    assert call.messages == tuple(HELLO)
    assert call.tools == (spec,)
    assert call.max_tokens == 50


async def test_echo_mode_repeats_the_last_user_message():
    model = MockChatModel()

    response = await model.complete(
        [Message.user("first"), Message.assistant("x"), Message.user("last")]
    )

    assert response.message.content == "echo: last"


async def test_echo_mode_without_a_user_message_is_still_valid():
    response = await MockChatModel().complete([Message.system("rules")])

    assert response.message.content == "echo: "


async def test_two_runs_with_the_same_input_are_identical():
    first = await MockChatModel().complete(HELLO)
    second = await MockChatModel().complete(HELLO)

    assert first == second
