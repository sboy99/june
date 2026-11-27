import pytest
from fake_tool import FakeTool

from june.composition import build_app
from june.config import Settings
from june.llm import ToolCall, ToolSpec
from june.runtime import GatedToolRunner
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
