import pytest

from june.llm import ChatResponse, Message, ToolCall, ToolResult, ToolSpec, Usage
from june.llm.adapters.mock import MockChatModel
from june.runtime import AgentLoop, GatedToolRunner, LoopStop
from june.safety import ToolGate, Verdict
from june.shared.errors import SafetyDenied

pytestmark = pytest.mark.unit

RISKS = {"read": "low", "write": "medium", "shell": "high"}


class FakeApprover:
    def __init__(self, answer: bool | Exception = True) -> None:
        self.answer = answer
        self.asked: list[tuple[str, dict]] = []

    async def approve(self, tool, arguments) -> bool:
        self.asked.append((tool, dict(arguments)))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class FakeJudge:
    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict
        self.subjects: list[str] = []

    async def judge(self, subject, question) -> Verdict:
        self.subjects.append(subject)
        return self.verdict


@pytest.mark.parametrize("tool", ["read", "write"])
async def test_low_and_medium_risk_run_without_asking(tool):
    approver = FakeApprover()

    await ToolGate(RISKS, approver).check(tool, {"x": 1})

    assert approver.asked == []


async def test_unknown_tool_is_high_risk_and_asks():
    approver = FakeApprover(True)

    await ToolGate(RISKS, approver).check("new_tool", {"x": 1})

    assert approver.asked == [("new_tool", {"x": 1})]


async def test_approver_receives_name_and_arguments():
    approver = FakeApprover(True)

    await ToolGate(RISKS, approver).check("shell", {"cmd": "ls"})

    assert approver.asked == [("shell", {"cmd": "ls"})]


async def test_rejection_denies():
    with pytest.raises(SafetyDenied):
        await ToolGate(RISKS, FakeApprover(False)).check("shell", {})


async def test_no_approver_denies_high_risk():
    with pytest.raises(SafetyDenied):
        await ToolGate(RISKS).check("shell", {})


async def test_approver_error_denies():
    with pytest.raises(SafetyDenied):
        await ToolGate(RISKS, FakeApprover(RuntimeError("down"))).check("shell", {})


async def test_judge_can_deny_medium_risk():
    judge = FakeJudge(Verdict("deny", "high", "bad args"))

    with pytest.raises(SafetyDenied):
        await ToolGate(RISKS, judge=judge).check("write", {"path": "x"})
    assert "write" in judge.subjects[0]


async def test_decisions_and_approvals_are_logged_without_arguments(log_output):
    _, lines = log_output

    await ToolGate(RISKS, FakeApprover(True)).check("shell", {"cmd": "hunter2-argument"})

    entries = lines()
    assert any(line.get("gate") == "tool" and line["decision"] == "ask" for line in entries)
    assert any(line.get("approved") is True for line in entries)
    assert "hunter2-argument" not in str(entries)


class RecordingRunner:
    specs = (ToolSpec("shell", "run", {"type": "object"}),)

    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    async def run(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult(call.id, "ran")


async def test_gated_runner_lists_inner_specs_and_runs_allowed_calls():
    inner = RecordingRunner()
    gated = GatedToolRunner(inner, ToolGate(RISKS, FakeApprover(True)))

    result = await gated.run(ToolCall("c1", "shell", {}))

    assert gated.specs == inner.specs
    assert result.content == "ran"


async def test_denied_call_never_reaches_inner_runner():
    inner = RecordingRunner()
    gated = GatedToolRunner(inner, ToolGate(RISKS))

    with pytest.raises(SafetyDenied):
        await gated.run(ToolCall("c1", "shell", {}))
    assert inner.calls == []


def tool_use(call_id: str) -> ChatResponse:
    call = ToolCall(call_id, "shell", {"cmd": "ls"})
    return ChatResponse(Message.assistant("", tool_calls=(call,)), "tool_use", Usage(1, 0), "mock")


async def test_repeated_denied_calls_end_the_loop_as_loop_detected():
    inner = RecordingRunner()
    loop = AgentLoop(
        MockChatModel([tool_use(f"c{i}") for i in range(10)]),
        GatedToolRunner(inner, ToolGate(RISKS)),
    )

    result = await loop.run([Message.user("go")])

    assert result.stop is LoopStop.LOOP_DETECTED
    assert inner.calls == []
    assert any(
        m.tool_result and m.tool_result.is_error and "safety_denied" in m.tool_result.content
        for m in result.added
    )
