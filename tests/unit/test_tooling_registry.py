import pytest
from fake_tool import SCHEMA, FakeTool

from june.shared.errors import SafetyDenied, ToolError
from june.tooling import Tool, ToolRegistry

pytestmark = pytest.mark.unit


def test_fake_tool_satisfies_the_port():
    tool: Tool = FakeTool()

    assert tool.risk == "low"


async def test_runs_a_registered_tool_by_name():
    tool = FakeTool()
    registry = ToolRegistry([tool])

    result = await registry.run("fake", {"path": "a.txt"})

    assert result == "ok"
    assert tool.calls == [{"path": "a.txt"}]


def test_duplicate_names_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        ToolRegistry([FakeTool("a"), FakeTool("a")])


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_names_are_rejected(name):
    with pytest.raises(ValueError, match="blank"):
        ToolRegistry([FakeTool(name)])


def test_lists_definitions_and_risks():
    registry = ToolRegistry([FakeTool("a", "low"), FakeTool("b", "high")])

    assert [d.name for d in registry.definitions] == ["a", "b"]
    assert dict(registry.risks) == {"a": "low", "b": "high"}


def test_registry_copies_its_input():
    tools = [FakeTool("a")]
    registry = ToolRegistry(tools)

    tools.append(FakeTool("b"))

    assert [d.name for d in registry.definitions] == ["a"]


async def test_unknown_tool_raises_tool_error():
    with pytest.raises(ToolError, match="unknown tool"):
        await ToolRegistry([]).run("nope", {})


@pytest.mark.parametrize(
    ("arguments", "field"),
    [
        ({}, "path"),
        ({"path": 5}, "path"),
        ({"path": "x", "count": "3"}, "count"),
        ({"path": "x", "count": True}, "count"),
        ({"path": "x", "ratio": "hi"}, "ratio"),
        ({"path": "x", "flag": 1}, "flag"),
        ({"path": "x", "items": "no"}, "items"),
        ({"path": "x", "mode": "sk-planted-secret"}, "mode"),
        ({"path": "x", "extra": 1}, "extra"),
    ],
)
async def test_invalid_arguments_raise_naming_the_field_but_not_the_value(arguments, field):
    tool = FakeTool()
    registry = ToolRegistry([tool])

    with pytest.raises(ToolError) as info:
        await registry.run("fake", arguments)

    assert field in str(info.value)
    assert "sk-planted-secret" not in str(info.value)
    assert tool.calls == []


async def test_valid_optional_arguments_pass():
    registry = ToolRegistry([FakeTool()])

    result = await registry.run(
        "fake",
        {"path": "x", "count": 1, "ratio": 1.5, "flag": True, "items": [1], "mode": "r"},
    )

    assert result == "ok"
    assert SCHEMA["required"] == ["path"]


async def test_unknown_keys_pass_when_additional_properties_is_not_false():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    registry = ToolRegistry([FakeTool(parameters=schema)])

    assert await registry.run("fake", {"a": "x", "b": 1}) == "ok"


async def test_empty_schema_accepts_any_arguments():
    registry = ToolRegistry([FakeTool(parameters={})])

    assert await registry.run("fake", {"anything": 1}) == "ok"


async def test_unexpected_exception_becomes_generic_tool_error():
    registry = ToolRegistry([FakeTool(error=RuntimeError("boom sk-leak"))])

    with pytest.raises(ToolError) as info:
        await registry.run("fake", {"path": "x"})

    assert "boom" not in str(info.value)
    assert "sk-leak" not in str(info.value)


@pytest.mark.parametrize("error", [ToolError("bad input"), SafetyDenied("no")])
async def test_agent_errors_pass_through_unchanged(error):
    registry = ToolRegistry([FakeTool(error=error)])

    with pytest.raises(type(error)) as info:
        await registry.run("fake", {"path": "x"})

    assert info.value is error
