import asyncio

import pytest

from june.llm import ChatResponse, Message, ToolCall, ToolResult, ToolSpec, Usage
from june.llm.adapters.mock import MockChatModel
from june.runtime import COMPACTED_PLACEHOLDER, AgentLoop, Budget, Compactor, LoopStop
from june.shared import (
    DomainError,
    PermanentAdapterError,
    SafetyDenied,
    ToolError,
    TransientAdapterError,
)

pytestmark = pytest.mark.unit

SECRET = "sk-planted-secret-1234567890"
ECHO = ToolSpec("echo", "echo text", {"type": "object"})


def tool_use(*calls: ToolCall, tokens: int = 10) -> ChatResponse:
    return ChatResponse(
        message=Message.assistant("", tool_calls=calls),
        stop_reason="tool_use",
        usage=Usage(tokens, 0),
        model="mock",
    )


def call(call_id: str = "c1", name: str = "echo") -> ToolCall:
    return ToolCall(call_id, name, {"text": "hi"})


def answer(text: str = "done", tokens: int = 1) -> ChatResponse:
    return ChatResponse(Message.assistant(text), "end_turn", Usage(tokens, 0), "mock")


class FakeTools:
    def __init__(self, outcomes=None, specs=(ECHO,)):
        self.specs = tuple(specs)
        self.outcomes = outcomes or {}
        self.calls: list[ToolCall] = []

    async def run(self, tool_call: ToolCall) -> ToolResult:
        self.calls.append(tool_call)
        outcome = self.outcomes.get(tool_call.name, f"ran {tool_call.name}")
        if isinstance(outcome, BaseException):
            raise outcome
        return ToolResult(tool_call.id, outcome)


INPUT = (Message.system("persona"), Message.user("hello"))


async def test_final_answer_ends_the_loop_as_answered():
    loop = AgentLoop(MockChatModel(["hi there"]))

    result = await loop.run(INPUT)

    assert (result.stop, result.reply, result.steps) == (LoopStop.ANSWERED, "hi there", 1)
    assert [m.content for m in result.added] == ["hi there"]


async def test_tool_calls_run_in_order_and_results_are_fed_back():
    model = MockChatModel([tool_use(call("a"), call("b", "other")), answer("ok")])
    tools = FakeTools(specs=(ECHO, ToolSpec("other", "another tool")))

    result = await AgentLoop(model, tools).run(INPUT)

    assert [c.id for c in tools.calls] == ["a", "b"]
    second_call = model.calls[1].messages
    assert [m.role for m in second_call[-3:]] == ["assistant", "tool", "tool"]
    assert [m.tool_result.content for m in second_call[-2:] if m.tool_result] == [
        "ran echo",
        "ran other",
    ]
    assert (result.stop, result.steps, result.reply) == (LoopStop.ANSWERED, 2, "ok")


async def test_tool_specs_are_offered_to_the_model_and_omitted_without_a_runner():
    with_tools, without = MockChatModel(["x"]), MockChatModel(["x"])

    await AgentLoop(with_tools, FakeTools()).run(INPUT)
    await AgentLoop(without).run(INPUT)

    assert with_tools.calls[0].tools == (ECHO,)
    assert without.calls[0].tools == ()


@pytest.mark.parametrize(
    "error, code",
    [(ToolError("disk on fire"), "tool_error"), (SafetyDenied("no way"), "safety_denied")],
)
async def test_expected_tool_errors_become_error_results_and_are_not_retried(error, code):
    model = MockChatModel([tool_use(call()), answer("sorry")])
    tools = FakeTools({"echo": error})

    result = await AgentLoop(model, tools).run(INPUT)

    tool_message = result.added[1]
    assert tool_message.tool_result.is_error and code in tool_message.content
    assert len(tools.calls) == 1
    assert result.stop is LoopStop.ANSWERED


async def test_unexpected_tool_exception_is_generic_for_the_model():
    model = MockChatModel([tool_use(call()), answer()])
    tools = FakeTools({"echo": RuntimeError(f"boom {SECRET}")})

    result = await AgentLoop(model, tools).run(INPUT)

    content = result.added[1].content
    assert result.added[1].tool_result.is_error
    assert SECRET not in content and "boom" not in content


async def test_secrets_in_tool_error_text_are_redacted():
    model = MockChatModel([tool_use(call()), answer()])
    tools = FakeTools({"echo": ToolError(f"auth failed with {SECRET}")})

    result = await AgentLoop(model, tools).run(INPUT)

    assert SECRET not in result.added[1].content


@pytest.mark.parametrize("tools", [None, FakeTools(specs=())])
async def test_unknown_tool_gets_an_error_result(tools):
    model = MockChatModel([tool_use(call(name="nope")), answer()])

    result = await AgentLoop(model, tools).run(INPUT)

    assert result.added[1].tool_result.is_error
    assert "nope" in result.added[1].content
    assert result.stop is LoopStop.ANSWERED


async def test_step_limit_stops_with_max_steps_and_answers_every_tool_call():
    model = MockChatModel([tool_use(call(f"c{n}")) for n in range(5)])

    result = await AgentLoop(model, FakeTools(), Budget(max_steps=2)).run(INPUT)

    assert (result.stop, result.steps, result.reply) == (LoopStop.MAX_STEPS, 2, "")
    assert [m.role for m in result.added] == ["assistant", "tool", "assistant", "tool"]


async def test_token_budget_stops_before_the_next_model_call():
    model = MockChatModel([tool_use(call(), tokens=100), answer()])

    result = await AgentLoop(model, FakeTools(), Budget(max_total_tokens=100)).run(INPUT)

    assert result.stop is LoopStop.TOKEN_BUDGET
    assert len(model.calls) == 1
    assert result.usage.total_tokens == 100


async def test_usage_is_summed_across_steps():
    model = MockChatModel([tool_use(call(), tokens=10), answer(tokens=5)])

    result = await AgentLoop(model, FakeTools()).run(INPUT)

    assert result.usage.total_tokens == 15


async def test_truncated_reply_ends_as_truncated_with_the_partial_text():
    cut = ChatResponse(Message.assistant("par"), "max_tokens", Usage(1, 1), "mock")

    result = await AgentLoop(MockChatModel([cut])).run(INPUT)

    assert (result.stop, result.reply) == (LoopStop.TRUNCATED, "par")


async def test_retryable_model_error_is_retried_then_succeeds():
    model = MockChatModel([TransientAdapterError("flaky"), "fine"])

    result = await AgentLoop(model).run(INPUT)

    assert (result.stop, result.reply, len(model.calls)) == (LoopStop.ANSWERED, "fine", 2)


async def test_exhausted_retries_end_with_model_error_and_the_code():
    model = MockChatModel([TransientAdapterError("flaky")] * 3)

    result = await AgentLoop(model, max_model_retries=2).run(INPUT)

    assert (result.stop, result.error_code, len(model.calls)) == (
        LoopStop.MODEL_ERROR,
        "adapter_transient",
        3,
    )
    assert result.reply == ""


async def test_permanent_model_error_is_not_retried():
    model = MockChatModel([PermanentAdapterError("bad key"), "never"])

    result = await AgentLoop(model).run(INPUT)

    assert (result.stop, result.error_code, len(model.calls)) == (
        LoopStop.MODEL_ERROR,
        "adapter_permanent",
        1,
    )


async def test_unexpected_model_exceptions_propagate():
    class Broken:
        async def complete(self, messages, *, tools=(), max_tokens=None):
            raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        await AgentLoop(Broken()).run(INPUT)


async def test_cancellation_propagates_from_a_tool():
    model = MockChatModel([tool_use(call()), answer()])
    tools = FakeTools({"echo": asyncio.CancelledError()})

    with pytest.raises(asyncio.CancelledError):
        await AgentLoop(model, tools).run(INPUT)


async def test_empty_messages_are_rejected():
    with pytest.raises(DomainError):
        await AgentLoop(MockChatModel(["x"])).run(())


@pytest.mark.parametrize("kwargs", [{"max_steps": 0}, {"max_total_tokens": 0}])
def test_invalid_budgets_are_rejected(kwargs):
    with pytest.raises(DomainError):
        Budget(**kwargs)


def test_negative_retry_count_is_rejected():
    with pytest.raises(DomainError):
        AgentLoop(MockChatModel(), max_model_retries=-1)


class Clock:
    """Fake monotonic clock: each reading advances time by `tick`."""

    def __init__(self, tick: float):
        self._now, self._tick = 0.0, tick

    def __call__(self) -> float:
        self._now += self._tick
        return self._now


async def test_time_budget_stops_the_loop_before_the_next_model_call():
    model = MockChatModel([tool_use(call("a")), tool_use(call("b", "echo")), answer()])
    loop = AgentLoop(model, FakeTools(), Budget(max_seconds=2.5), monotonic=Clock(1.0))

    result = await loop.run(INPUT)

    assert result.stop is LoopStop.TIME_BUDGET
    assert len(model.calls) == result.steps


async def test_a_run_inside_the_time_limit_is_unaffected():
    loop = AgentLoop(MockChatModel(["hi"]), budget=Budget(max_seconds=100), monotonic=Clock(0.1))

    assert (await loop.run(INPUT)).stop is LoopStop.ANSWERED


async def test_identical_repeated_calls_end_the_run_as_loop_detected():
    repeat = tool_use(call("a"))
    model = MockChatModel([repeat, tool_use(call("b")), tool_use(call("c")), answer()])
    tools = FakeTools()

    result = await AgentLoop(model, tools, Budget(max_repeated_calls=3)).run(INPUT)

    assert result.stop is LoopStop.LOOP_DETECTED
    assert result.steps == 3
    assert len(tools.calls) == 2
    last = result.added[-1]
    assert last.tool_result.call_id == "c" and last.tool_result.is_error


async def test_every_call_of_the_detecting_response_is_answered():
    first = tool_use(call("a"))
    second = tool_use(call("b"), call("c", "other"))
    model = MockChatModel([first, second])
    tools = FakeTools(specs=(ECHO, ToolSpec("other", "another tool")))

    result = await AgentLoop(model, tools, Budget(max_repeated_calls=2)).run(INPUT)

    answered = [m.tool_result.call_id for m in result.added if m.tool_result]
    assert result.stop is LoopStop.LOOP_DETECTED
    assert answered == ["a", "b", "c"]


async def test_calls_with_different_arguments_are_not_a_loop():
    def varied(call_id: str, text: str) -> ChatResponse:
        return tool_use(ToolCall(call_id, "echo", {"text": text}))

    model = MockChatModel([varied("a", "1"), varied("b", "2"), varied("c", "3"), answer()])

    result = await AgentLoop(model, FakeTools(), Budget(max_repeated_calls=2)).run(INPUT)

    assert result.stop is LoopStop.ANSWERED


@pytest.mark.parametrize(
    "kwargs", [{"max_seconds": 0}, {"max_seconds": -1.0}, {"max_repeated_calls": 1}]
)
def test_invalid_time_and_repeat_limits_are_rejected(kwargs):
    with pytest.raises(DomainError):
        Budget(**kwargs)


async def test_compaction_shrinks_the_prompt_but_added_keeps_full_tool_output():
    big = "x" * 500
    model = MockChatModel(
        [tool_use(call("a")), tool_use(call("b", "other")), tool_use(call("c", "third")), answer()]
    )
    tools = FakeTools(
        {"echo": big, "other": big, "third": big},
        specs=(ECHO, ToolSpec("other", "o"), ToolSpec("third", "t")),
    )
    loop = AgentLoop(model, tools, compactor=Compactor(max_chars=800, keep_recent=2))

    result = await loop.run(INPUT)

    last_prompt = model.calls[-1].messages
    prompt_tool_text = [m.content for m in last_prompt if m.role == "tool"]
    assert COMPACTED_PLACEHOLDER in prompt_tool_text
    assert [m.content for m in result.added if m.role == "tool"] == [big, big, big]
    assert result.stop is LoopStop.ANSWERED
