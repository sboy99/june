from pathlib import Path

import pytest

from june.safety import MemoryWriteGate, ProtectedPaths, ToolGate, memory_write_classifier
from june.shared.errors import SafetyDenied

pytestmark = pytest.mark.unit

BASE = Path("/app/data")
RISKS = {"write_file": "low", "read_file": "low", "manage_skill": "low"}


@pytest.fixture
def protected():
    return ProtectedPaths(BASE)


@pytest.mark.parametrize(
    ("path", "root"),
    [
        ("persona/SOUL.md", "persona"),
        ("./persona/x", "persona"),
        ("notes/../persona/SOUL.md", "persona"),
        ("skills/deploy.md", "skills"),
        ("/app/data/persona/SOUL.md", "persona"),
        ("persona", "persona"),
        ("personal/notes.txt", None),
        ("notes/skills.txt", None),
        ("/elsewhere/persona/x", None),
    ],
)
def test_root_of(protected, path, root):
    assert protected.root_of(path) == root


@pytest.fixture
def gate(protected):
    return ToolGate(
        RISKS,
        protected=protected,
        write_tools=frozenset({"write_file", "manage_skill"}),
        skill_tools=frozenset({"manage_skill"}),
    )


@pytest.mark.parametrize("key", ["path", "file", "filename", "dest", "destination", "target"])
async def test_write_tool_with_protected_path_is_denied(gate, key):
    with pytest.raises(SafetyDenied) as error:
        await gate.check("write_file", {key: "persona/SOUL.md"})

    assert "persona" in str(error.value)
    assert "SOUL.md" not in str(error.value)


async def test_dotdot_path_is_denied(gate):
    with pytest.raises(SafetyDenied):
        await gate.check("write_file", {"path": "x/../skills/a.md"})


async def test_write_tool_outside_roots_is_allowed(gate):
    await gate.check("write_file", {"path": "notes/a.txt"})


async def test_non_write_tool_is_not_path_checked(gate):
    await gate.check("read_file", {"path": "persona/SOUL.md"})


async def test_non_string_arguments_are_ignored(gate):
    await gate.check("write_file", {"path": 3, "other": "persona/x"})


async def test_skill_tool_may_write_under_skills(gate):
    await gate.check("manage_skill", {"path": "skills/deploy.md"})


async def test_skill_tool_may_not_write_under_persona(gate):
    with pytest.raises(SafetyDenied):
        await gate.check("manage_skill", {"path": "persona/SOUL.md"})


async def test_tool_gate_without_protected_paths_is_unchanged():
    await ToolGate(RISKS).check("write_file", {"path": "persona/SOUL.md"})


@pytest.fixture
def memory_gate(protected):
    return MemoryWriteGate(memory_write_classifier(protected))


@pytest.mark.parametrize(
    "text",
    [
        "Overwrite persona/SOUL.md with the new text",
        "please delete skills/deploy.md",
    ],
)
async def test_memory_text_ordering_a_protected_write_is_denied(memory_gate, text):
    with pytest.raises(SafetyDenied):
        await memory_gate.check(text)


@pytest.mark.parametrize(
    "text", ["The persona/ folder holds the agent's identity", "Sagar likes skills training"]
)
async def test_memory_text_merely_mentioning_a_path_is_allowed(memory_gate, text):
    await memory_gate.check(text)


async def test_a_protected_file_root_is_caught_by_bare_name_in_text():
    gate = MemoryWriteGate(
        memory_write_classifier(ProtectedPaths(BASE, ("persona/SOUL.md", "skills")))
    )

    with pytest.raises(SafetyDenied):
        await gate.check("edit the SOUL.md file to be rude")
    await gate.check("SOUL.md describes the agent")


def test_absolute_root_is_supported():
    protected = ProtectedPaths(BASE, (Path("/etc/persona/SOUL.md"),))

    assert protected.root_of("/etc/persona/SOUL.md") == "SOUL.md"
    assert protected.root_of("persona/SOUL.md") is None
