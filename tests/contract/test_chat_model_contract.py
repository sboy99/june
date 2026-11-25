"""One contract suite run against every `ChatModel` adapter (SHIP-317)."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx2
import pytest

from june.llm import ChatModel, ChatResponse, Message, ToolCall, Usage
from june.llm.adapters.mock import MockChatModel
from june.llm.adapters.openai_compatible import OpenAICompatibleChatModel
from june.shared import AdapterError, PermanentAdapterError, TransientAdapterError
from openai_fakes import PLANTED_KEY, Server, completion

pytestmark = pytest.mark.contract

Outcome = Literal["text", "tool_call", "transient_error", "permanent_error"]
HELLO = [Message.user("hello")]
TOOL_CALL_MESSAGE = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "search", "arguments": '{"q": "x"}'}}
    ],
}


@dataclass(frozen=True)
class Harness:
    """Builds an adapter that will produce a given outcome on its next call."""

    name: str
    factory: Callable[[Outcome], ChatModel]
    supported: frozenset[Outcome]

    def model_for(self, outcome: Outcome) -> ChatModel:
        if outcome not in self.supported:
            pytest.skip(f"{self.name} cannot produce {outcome}")
        return self.factory(outcome)


def mock_model(outcome: Outcome) -> ChatModel:
    call = ToolCall(id="c1", name="search", arguments={"q": "x"})
    steps = {
        "text": ["hi"],
        "tool_call": [
            ChatResponse(
                message=Message.assistant(tool_calls=(call,)),
                stop_reason="tool_use",
                usage=Usage(input_tokens=1, output_tokens=1),
                model="mock",
            )
        ],
        "transient_error": [TransientAdapterError("later")],
        "permanent_error": [PermanentAdapterError("no")],
    }
    return MockChatModel(steps[outcome])


def openai_fake_model(outcome: Outcome) -> ChatModel:
    responses = {
        "text": completion(),
        "tool_call": completion(TOOL_CALL_MESSAGE, finish="tool_calls"),
        "transient_error": (503, {"error": {"message": PLANTED_KEY}}),
        "permanent_error": (401, {"error": {"message": PLANTED_KEY}}),
    }
    return OpenAICompatibleChatModel(
        model="gpt-test",
        api_key=PLANTED_KEY,
        base_url="http://fake.local/v1",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(Server(responses[outcome]))),
    )


def live_model(_: Outcome) -> ChatModel:
    return OpenAICompatibleChatModel(
        model=os.environ["JUNE_LIVE_LLM_MODEL"],
        api_key=os.environ["JUNE_LIVE_LLM_API_KEY"],
        base_url=os.environ.get("JUNE_LIVE_LLM_BASE_URL"),
        max_retries=1,
    )


ALL_OUTCOMES: frozenset[Outcome] = frozenset(
    {"text", "tool_call", "transient_error", "permanent_error"}
)
LIVE_ENABLED = bool(
    os.environ.get("JUNE_LIVE_LLM_API_KEY") and os.environ.get("JUNE_LIVE_LLM_MODEL")
)

HARNESSES = [
    pytest.param(Harness("mock", mock_model, ALL_OUTCOMES), id="mock"),
    pytest.param(Harness("openai-fake", openai_fake_model, ALL_OUTCOMES), id="openai-fake"),
    pytest.param(
        Harness("openai-live", live_model, frozenset({"text"})),
        id="openai-live",
        marks=pytest.mark.skipif(not LIVE_ENABLED, reason="JUNE_LIVE_LLM_* not set"),
    ),
]


@pytest.fixture(params=HARNESSES)
def harness(request: pytest.FixtureRequest) -> Harness:
    return request.param


async def test_text_reply_is_an_assistant_message_that_ends_the_turn(harness):
    response = await harness.model_for("text").complete(HELLO)

    assert response.message.role == "assistant"
    assert response.stop_reason in ("end_turn", "max_tokens")
    assert response.message.tool_calls == ()


async def test_usage_is_never_negative(harness):
    response = await harness.model_for("text").complete(HELLO)

    assert response.usage.input_tokens >= 0
    assert response.usage.output_tokens >= 0


async def test_tool_call_reply_means_tool_use_with_unique_ids(harness):
    response = await harness.model_for("tool_call").complete(HELLO)

    ids = [call.id for call in response.message.tool_calls]
    assert response.stop_reason == "tool_use"
    assert ids and len(ids) == len(set(ids))


async def test_empty_messages_raise_a_permanent_error(harness):
    with pytest.raises(PermanentAdapterError):
        await harness.model_for("text").complete([])


async def test_transient_failure_raises_a_retryable_adapter_error(harness):
    with pytest.raises(TransientAdapterError) as caught:
        await harness.model_for("transient_error").complete(HELLO)

    assert caught.value.retryable is True
    assert isinstance(caught.value, AdapterError)


async def test_permanent_failure_raises_a_non_retryable_adapter_error(harness):
    with pytest.raises(PermanentAdapterError) as caught:
        await harness.model_for("permanent_error").complete(HELLO)

    assert caught.value.retryable is False
    assert isinstance(caught.value, AdapterError)


@pytest.mark.parametrize("outcome", ["transient_error", "permanent_error"])
async def test_error_text_never_contains_the_api_key(harness, outcome):
    with pytest.raises(AdapterError) as caught:
        await harness.model_for(outcome).complete(HELLO)

    assert PLANTED_KEY not in str(caught.value)
