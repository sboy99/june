import os
import stat
from pathlib import Path

import pytest

from june.shared.errors import ToolError
from june.tooling.adapters.files import MAX_FILE_BYTES, ReadFileTool, WriteFileTool

pytestmark = pytest.mark.unit


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    return root


@pytest.fixture
def outside(tmp_path):
    folder = tmp_path / "outside"
    folder.mkdir()
    (folder / "secret.txt").write_text("secret", encoding="utf-8")
    return folder


def test_definitions_and_risk():
    read, write = ReadFileTool(Path("x")), WriteFileTool(Path("x"), ())

    assert (read.definition.name, read.risk) == ("read_file", "low")
    assert (write.definition.name, write.risk) == ("write_file", "high")


async def test_reads_a_relative_file(workspace):
    (workspace / "a.txt").write_text("hello", encoding="utf-8")

    assert await ReadFileTool(workspace).run({"path": "a.txt"}) == "hello"


async def test_reads_an_absolute_path_inside_the_workspace(workspace):
    target = workspace / "a.txt"
    target.write_text("hi", encoding="utf-8")

    assert await ReadFileTool(workspace).run({"path": str(target)}) == "hi"


@pytest.mark.parametrize("path", ["../outside/secret.txt", "sub/../../outside/secret.txt"])
async def test_read_refuses_dotdot_escape(workspace, outside, path):
    with pytest.raises(ToolError, match="read_file"):
        await ReadFileTool(workspace).run({"path": path})


async def test_read_refuses_absolute_path_outside(workspace, outside):
    with pytest.raises(ToolError, match="outside the workspace"):
        await ReadFileTool(workspace).run({"path": str(outside / "secret.txt")})


async def test_read_refuses_symlinked_file_escape(workspace, outside):
    os.symlink(outside / "secret.txt", workspace / "link.txt")

    with pytest.raises(ToolError, match="outside the workspace"):
        await ReadFileTool(workspace).run({"path": "link.txt"})


async def test_read_refuses_symlinked_parent_escape(workspace, outside):
    os.symlink(outside, workspace / "linkdir")

    with pytest.raises(ToolError, match="outside the workspace"):
        await ReadFileTool(workspace).run({"path": "linkdir/secret.txt"})


async def test_read_follows_symlink_that_stays_inside(workspace):
    (workspace / "real.txt").write_text("ok", encoding="utf-8")
    os.symlink(workspace / "real.txt", workspace / "alias.txt")

    assert await ReadFileTool(workspace).run({"path": "alias.txt"}) == "ok"


async def test_read_missing_file_is_a_tool_error(workspace):
    with pytest.raises(ToolError, match="not found"):
        await ReadFileTool(workspace).run({"path": "nope.txt"})


async def test_read_directory_is_a_tool_error(workspace):
    (workspace / "d").mkdir()

    with pytest.raises(ToolError, match="not a file"):
        await ReadFileTool(workspace).run({"path": "d"})


async def test_read_non_utf8_is_a_tool_error(workspace):
    (workspace / "b.bin").write_bytes(b"\xff\xfe\x00")

    with pytest.raises(ToolError, match="UTF-8"):
        await ReadFileTool(workspace).run({"path": "b.bin"})


async def test_read_refuses_files_over_the_limit(workspace):
    (workspace / "big.txt").write_text("x" * 11, encoding="utf-8")

    with pytest.raises(ToolError, match="too large"):
        await ReadFileTool(workspace, max_bytes=10).run({"path": "big.txt"})


async def test_read_allows_file_at_the_limit(workspace):
    (workspace / "ok.txt").write_text("x" * 10, encoding="utf-8")

    assert await ReadFileTool(workspace, max_bytes=10).run({"path": "ok.txt"}) == "x" * 10


def test_default_limit_is_one_mebibyte():
    assert MAX_FILE_BYTES == 1024 * 1024


async def test_read_error_does_not_echo_contents(workspace):
    (workspace / "s.txt").write_text("TOPSECRET" * 5, encoding="utf-8")

    with pytest.raises(ToolError) as info:
        await ReadFileTool(workspace, max_bytes=3).run({"path": "s.txt"})

    assert "TOPSECRET" not in str(info.value)


async def test_write_creates_file_and_parent_dirs(workspace):
    result = await WriteFileTool(workspace, ()).run({"path": "a/b/c.txt", "content": "data"})

    assert (workspace / "a/b/c.txt").read_text(encoding="utf-8") == "data"
    assert "a/b/c.txt" in result


async def test_write_overwrites_and_leaves_no_temp_files(workspace):
    (workspace / "a.txt").write_text("old", encoding="utf-8")

    await WriteFileTool(workspace, ()).run({"path": "a.txt", "content": "new"})

    assert (workspace / "a.txt").read_text(encoding="utf-8") == "new"
    assert [p.name for p in workspace.iterdir()] == ["a.txt"]


async def test_write_refuses_dotdot_escape(workspace, outside):
    with pytest.raises(ToolError, match="write_file"):
        await WriteFileTool(workspace, ()).run({"path": "../outside/x.txt", "content": "x"})

    assert not (outside / "x.txt").exists()


async def test_write_refuses_absolute_path_outside(workspace, outside):
    with pytest.raises(ToolError, match="outside the workspace"):
        await WriteFileTool(workspace, ()).run({"path": str(outside / "x.txt"), "content": "x"})


async def test_write_refuses_symlinked_file_escape(workspace, outside):
    os.symlink(outside / "secret.txt", workspace / "link.txt")

    with pytest.raises(ToolError, match="outside the workspace"):
        await WriteFileTool(workspace, ()).run({"path": "link.txt", "content": "pwn"})

    assert (outside / "secret.txt").read_text(encoding="utf-8") == "secret"


async def test_write_refuses_symlinked_parent_escape(workspace, outside):
    os.symlink(outside, workspace / "linkdir")

    with pytest.raises(ToolError, match="outside the workspace"):
        await WriteFileTool(workspace, ()).run({"path": "linkdir/new/x.txt", "content": "x"})

    assert not (outside / "new").exists()


async def test_write_refuses_dangling_symlink_escape(workspace, outside):
    os.symlink(outside / "created.txt", workspace / "dangling.txt")

    with pytest.raises(ToolError, match="outside the workspace"):
        await WriteFileTool(workspace, ()).run({"path": "dangling.txt", "content": "x"})

    assert not (outside / "created.txt").exists()


@pytest.mark.parametrize(
    "path", ["persona/SOUL.md", "persona", "skills/a/SKILL.md", "x/../skills/a.md"]
)
async def test_write_refuses_protected_roots_inside_workspace(workspace, path):
    roots = (workspace / "persona", workspace / "skills")

    with pytest.raises(ToolError, match="protected"):
        await WriteFileTool(workspace, roots).run({"path": path, "content": "x"})

    assert not (workspace / "skills").exists()


async def test_write_refuses_protected_root_reached_through_symlink(workspace):
    (workspace / "skills").mkdir()
    os.symlink(workspace / "skills", workspace / "alias")

    with pytest.raises(ToolError, match="protected"):
        await WriteFileTool(workspace, (workspace / "skills",)).run(
            {"path": "alias/a.md", "content": "x"}
        )


async def test_write_allows_sibling_with_shared_prefix(workspace):
    await WriteFileTool(workspace, (workspace / "skills",)).run(
        {"path": "skills-extra/a.md", "content": "x"}
    )

    assert (workspace / "skills-extra/a.md").exists()


async def test_write_refuses_content_over_the_limit(workspace):
    with pytest.raises(ToolError, match="too large"):
        await WriteFileTool(workspace, (), max_bytes=4).run({"path": "a.txt", "content": "héllo"})

    assert not (workspace / "a.txt").exists()


async def test_write_refuses_a_directory_target(workspace):
    (workspace / "d").mkdir()

    with pytest.raises(ToolError, match="directory"):
        await WriteFileTool(workspace, ()).run({"path": "d", "content": "x"})


async def test_failed_write_keeps_the_original_file(workspace, monkeypatch):
    (workspace / "a.txt").write_text("old", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(ToolError, match="could not write"):
        await WriteFileTool(workspace, ()).run({"path": "a.txt", "content": "new"})

    assert (workspace / "a.txt").read_text(encoding="utf-8") == "old"
    assert [p.name for p in workspace.iterdir()] == ["a.txt"]


@pytest.mark.parametrize("path", ["Persona/soul.md", "SKILLS/x", "PERSONA"])
async def test_write_refuses_protected_roots_in_other_letter_case(workspace, path):
    roots = (workspace / "persona", workspace / "skills")

    with pytest.raises(ToolError, match="protected"):
        await WriteFileTool(workspace, roots).run({"path": path, "content": "x"})

    assert list(workspace.iterdir()) == []


async def test_overwrite_preserves_the_existing_file_mode(workspace):
    target = workspace / "a.txt"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o640)

    await WriteFileTool(workspace, ()).run({"path": "a.txt", "content": "new"})

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


async def test_new_file_gets_the_umask_default_mode(workspace):
    previous = os.umask(0o022)
    try:
        await WriteFileTool(workspace, ()).run({"path": "n.txt", "content": "x"})
    finally:
        os.umask(previous)

    assert stat.S_IMODE((workspace / "n.txt").stat().st_mode) == 0o644


async def test_failed_write_removes_parent_directories_it_created(workspace, monkeypatch):
    (workspace / "keep").mkdir()

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(ToolError, match="could not write"):
        await WriteFileTool(workspace, ()).run({"path": "keep/a/b/c.txt", "content": "x"})

    assert [p.name for p in workspace.iterdir()] == ["keep"]
    assert list((workspace / "keep").iterdir()) == []


@pytest.mark.parametrize("arguments", [{}, {"path": 3}, {"path": None}])
async def test_read_with_bad_arguments_is_a_tool_error(workspace, arguments):
    with pytest.raises(ToolError, match="read_file"):
        await ReadFileTool(workspace).run(arguments)


@pytest.mark.parametrize(
    "arguments", [{}, {"path": "a.txt"}, {"content": "x"}, {"path": "a.txt", "content": 5}]
)
async def test_write_with_bad_arguments_is_a_tool_error(workspace, arguments):
    with pytest.raises(ToolError, match="write_file"):
        await WriteFileTool(workspace, ()).run(arguments)
