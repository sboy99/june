import pytest
from fake_tool import FakeTool

from june.composition import build_app
from june.config import Settings
from june.llm import ToolCall, ToolSpec
from june.runtime import GatedToolRunner
from june.safety import ToolGate
from june.shared.errors import SafetyDenied, ToolError
from june.tool_runner import RegistryToolRunner
from june.tooling import ToolRegistry

pytestmark = pytest.mark.unit


def test_specs_map_definitions():
    runner = RegistryToolRunner(ToolRegistry([FakeTool("a")]))

    assert [s.name for s in runner.specs] == ["a"]
    assert isinstance(runner.specs[0], ToolSpec)
    assert runner.specs[0].description == "a fake tool"
    assert runner.specs[0].parameters["required"] == ["path"]


async def test_run_wraps_text_in_a_result_with_the_call_id():
    runner = RegistryToolRunner(ToolRegistry([FakeTool("a")]))

    result = await runner.run(ToolCall("c1", "a", {"path": "x"}))

    assert (result.call_id, result.content, result.is_error) == ("c1", "ok", False)


async def test_run_propagates_tool_errors():
    runner = RegistryToolRunner(ToolRegistry([]))

    with pytest.raises(ToolError):
        await runner.run(ToolCall("c1", "nope", {}))


async def test_built_app_gates_every_call(tmp_path):
    persona = tmp_path / "SOUL.md"
    persona.write_text("be kind", encoding="utf-8")
    app = build_app(Settings(persona_path=persona, data_dir=tmp_path))

    assert isinstance(app.tool_runner, GatedToolRunner)
    assert list(app.tool_runner.specs) == []
    with pytest.raises(SafetyDenied):
        await app.tool_runner.run(ToolCall("c1", "unknown", {}))


class _Approver:
    def __init__(self, answer: bool) -> None:
        self.asked: list[str] = []
        self._answer = answer

    async def approve(self, tool, arguments) -> bool:
        self.asked.append(tool)
        return self._answer


def _gated(tool, approver=None):
    registry = ToolRegistry([tool])
    gate = ToolGate(registry.risks, approver)
    return GatedToolRunner(RegistryToolRunner(registry), gate)


async def test_registered_high_risk_tool_asks_the_approver():
    approver = _Approver(True)
    tool = FakeTool("danger", "high")

    result = await _gated(tool, approver).run(ToolCall("c1", "danger", {"path": "x"}))

    assert approver.asked == ["danger"]
    assert result.content == "ok"


async def test_registered_high_risk_tool_is_denied_without_an_approver():
    tool = FakeTool("danger", "high")

    with pytest.raises(SafetyDenied):
        await _gated(tool).run(ToolCall("c1", "danger", {"path": "x"}))

    assert tool.calls == []


async def test_registered_low_risk_tool_runs_without_asking():
    approver = _Approver(False)
    tool = FakeTool("safe", "low")

    result = await _gated(tool, approver).run(ToolCall("c1", "safe", {"path": "x"}))

    assert approver.asked == []
    assert result.content == "ok"
