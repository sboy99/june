import json

import httpx2
import pytest

from june.llm import ChatModel, Message, ToolCall, ToolResult, ToolSpec
from june.llm.adapters.openai_compatible import OpenAICompatibleChatModel
from june.shared import PermanentAdapterError, TransientAdapterError
from openai_fakes import PLANTED_KEY, Server, completion

pytestmark = pytest.mark.unit


def make_model(server, **overrides):
    options = {
        "model": "gpt-test",
        "api_key": PLANTED_KEY,
        "base_url": "http://fake.local/v1",
        "max_retries": 0,
        "http_client": httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    }
    return OpenAICompatibleChatModel(**{**options, **overrides})


HELLO = [Message.user("hello")]


async def test_plain_reply_is_translated():
    server = Server(
        completion(usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})
    )
    model: ChatModel = make_model(server)

    response = await model.complete(HELLO)

    assert response.message == Message.assistant("hi")
    assert response.stop_reason == "end_turn"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (5, 2)
    assert response.model == "gpt-test"


async def test_missing_usage_is_reported_as_zero():
    response = await make_model(Server(completion())).complete(HELLO)

    assert response.usage.total_tokens == 0


async def test_conversation_is_serialized_to_the_wire_format():
    server = Server(completion())
    call = ToolCall(id="c1", name="search", arguments={"q": "x"})
    messages = [
        Message.system("rules"),
        Message.user("find x"),
        Message.assistant(tool_calls=(call,)),
        Message.tool(ToolResult(call_id="c1", content="found")),
    ]

    await make_model(server).complete(messages, max_tokens=64)

    body = server.last_body
    assert body["model"] == "gpt-test"
    assert body["max_tokens"] == 64
    assert body["messages"][0] == {"role": "system", "content": "rules"}
    assert body["messages"][1] == {"role": "user", "content": "find x"}
    assistant = body["messages"][2]
    assert assistant["tool_calls"][0]["id"] == "c1"
    assert assistant["tool_calls"][0]["function"]["name"] == "search"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"q": "x"}
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "found"}


async def test_tools_are_sent_as_function_tools():
    server = Server(completion())
    spec = ToolSpec(name="search", description="find", parameters={"type": "object"})

    await make_model(server).complete(HELLO, tools=[spec])

    assert server.last_body["tools"] == [
        {
            "type": "function",
            "function": {"name": "search", "description": "find", "parameters": {"type": "object"}},
        }
    ]


async def test_no_tools_field_is_sent_when_there_are_no_tools():
    server = Server(completion())

    await make_model(server).complete(HELLO)

    assert "tools" not in server.last_body


async def test_tool_calls_are_parsed_and_imply_tool_use():
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "x"}'},
            }
        ],
    }

    response = await make_model(Server(completion(message, finish="tool_calls"))).complete(HELLO)

    assert response.stop_reason == "tool_use"
    assert response.message.tool_calls == (ToolCall(id="c1", name="search", arguments={"q": "x"}),)


async def test_tool_calls_with_stop_finish_reason_still_mean_tool_use():
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}}
        ],
    }

    response = await make_model(Server(completion(message, finish="stop"))).complete(HELLO)

    assert response.stop_reason == "tool_use"


async def test_length_finish_maps_to_max_tokens():
    response = await make_model(Server(completion(finish="length"))).complete(HELLO)

    assert response.stop_reason == "max_tokens"


async def test_empty_messages_are_rejected_before_any_request():
    server = Server(completion())

    with pytest.raises(PermanentAdapterError):
        await make_model(server).complete([])

    assert server.requests == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_client_errors_are_permanent(status):
    model = make_model(Server((status, {"error": {"message": "nope"}})))

    with pytest.raises(PermanentAdapterError) as caught:
        await model.complete(HELLO)

    assert caught.value.retryable is False
    assert str(status) in str(caught.value)


@pytest.mark.parametrize("status", [408, 409, 429, 500, 503])
async def test_rate_limits_and_server_errors_are_transient(status):
    model = make_model(Server((status, {"error": {"message": "later"}})))

    with pytest.raises(TransientAdapterError) as caught:
        await model.complete(HELLO)

    assert caught.value.retryable is True


async def test_connection_failure_is_transient():
    model = make_model(Server(httpx2.ConnectError("refused")))

    with pytest.raises(TransientAdapterError):
        await model.complete(HELLO)


async def test_timeout_is_transient():
    model = make_model(Server(httpx2.ReadTimeout("slow")))

    with pytest.raises(TransientAdapterError):
        await model.complete(HELLO)


async def test_transient_failure_is_retried_then_succeeds():
    server = Server((500, {"error": {"message": "boom"}}), completion())
    model = make_model(server, max_retries=1)

    response = await model.complete(HELLO)

    assert response.message.content == "hi"
    assert len(server.requests) == 2


async def test_retries_are_bounded_by_the_configured_count():
    server = Server((500, {"error": {"message": "boom"}}))
    model = make_model(server, max_retries=1)

    with pytest.raises(TransientAdapterError):
        await model.complete(HELLO)

    assert len(server.requests) == 2


@pytest.mark.parametrize("arguments", ["not json", "[1, 2]"])
async def test_malformed_tool_arguments_are_permanent(arguments):
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "t", "arguments": arguments}}
        ],
    }

    with pytest.raises(PermanentAdapterError, match="arguments"):
        await make_model(Server(completion(message, finish="tool_calls"))).complete(HELLO)


async def test_unsupported_finish_reason_is_permanent():
    with pytest.raises(PermanentAdapterError, match="content_filter"):
        await make_model(Server(completion(finish="content_filter"))).complete(HELLO)


async def test_response_without_choices_is_permanent():
    body = {"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": []}

    with pytest.raises(PermanentAdapterError, match="choices"):
        await make_model(Server(body)).complete(HELLO)


async def test_api_key_is_sent_but_never_appears_in_errors():
    server = Server((401, {"error": {"message": f"bad key {PLANTED_KEY}"}}))
    model = make_model(server)

    with pytest.raises(PermanentAdapterError) as caught:
        await model.complete(HELLO)

    assert server.requests[0].headers["authorization"] == f"Bearer {PLANTED_KEY}"
    assert PLANTED_KEY not in str(caught.value)
