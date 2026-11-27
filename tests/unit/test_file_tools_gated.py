"""File tools behind the real ToolGate, GatedToolRunner and RegistryToolRunner."""

import pytest

from june.llm import ToolCall
from june.runtime import GatedToolRunner
from june.safety import ProtectedPaths, ToolGate
from june.shared.errors import SafetyDenied
from june.tool_runner import RegistryToolRunner
from june.tooling import ToolRegistry
from june.tooling.adapters.files import ReadFileTool, WriteFileTool

pytestmark = pytest.mark.unit


class FakeApprover:
    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked: list[str] = []

    async def approve(self, tool, arguments) -> bool:
        self.asked.append(tool)
        return self.answer


def build(workspace, approver):
    roots = (workspace / "persona", workspace / "skills")
    registry = ToolRegistry([ReadFileTool(workspace), WriteFileTool(workspace, roots)])
    gate = ToolGate(
        registry.risks,
        approver,
        protected=ProtectedPaths(workspace, ("persona", "skills")),
        write_tools=frozenset({"write_file"}),
    )
    return GatedToolRunner(RegistryToolRunner(registry), gate)


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


async def test_write_file_without_an_approver_is_denied(workspace):
    runner = build(workspace, None)

    with pytest.raises(SafetyDenied):
        await runner.run(ToolCall("c", "write_file", {"path": "a.txt", "content": "x"}))

    assert not (workspace / "a.txt").exists()


async def test_write_file_asks_the_approver_and_runs_when_approved(workspace):
    approver = FakeApprover(True)

    await build(workspace, approver).run(
        ToolCall("c", "write_file", {"path": "a.txt", "content": "x"})
    )

    assert approver.asked == ["write_file"]
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "x"


async def test_write_file_denied_by_the_approver_does_not_write(workspace):
    approver = FakeApprover(False)

    with pytest.raises(SafetyDenied):
        await build(workspace, approver).run(
            ToolCall("c", "write_file", {"path": "a.txt", "content": "x"})
        )

    assert not (workspace / "a.txt").exists()


async def test_protected_path_write_is_denied_without_asking(workspace):
    approver = FakeApprover(True)

    with pytest.raises(SafetyDenied, match="protected"):
        await build(workspace, approver).run(
            ToolCall("c", "write_file", {"path": "persona/soul.md", "content": "x"})
        )

    assert approver.asked == []
    assert not (workspace / "persona").exists()


async def test_read_file_runs_without_asking(workspace):
    (workspace / "a.txt").write_text("hi", encoding="utf-8")
    approver = FakeApprover(False)

    result = await build(workspace, approver).run(ToolCall("c", "read_file", {"path": "a.txt"}))

    assert result.content == "hi"
    assert approver.asked == []
