"""Confined file tools: read and write text files inside the Workspace only.

Every path is resolved (symlinks followed) and must stay inside the Workspace.
Errors name the tool and the reason, never file contents.
"""

import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from june.shared.errors import ToolError
from june.tooling.ports import RiskLevel, ToolDefinition

MAX_FILE_BYTES = 1024 * 1024
_PATH_PROPERTY = {"type": "string", "description": "File path, relative to the workspace."}


class WorkspacePath:
    """Resolves model-supplied paths and refuses any that leave the Workspace."""

    def __init__(self, workspace: Path) -> None:
        self._root = workspace.resolve()

    def resolve(self, tool: str, path: str) -> Path:
        """Return the fully resolved target, or raise `ToolError` if it escapes the Workspace.

        A relative `path` is taken from the Workspace root. Resolution follows every symlink,
        including a dangling final link, so the check sees where an operation would land.
        """
        if not path.strip() or "\0" in path:
            raise ToolError(f"{tool}: invalid path")
        try:
            target = (self._root / path).resolve()
        except (OSError, RuntimeError) as exc:
            raise ToolError(f"{tool}: path could not be resolved") from exc
        if not target.is_relative_to(self._root):
            raise ToolError(f"{tool}: path is outside the workspace")
        return target


class ReadFileTool:
    """Read a UTF-8 text file from the Workspace."""

    risk: RiskLevel = "low"

    def __init__(self, workspace: Path, max_bytes: int = MAX_FILE_BYTES) -> None:
        self._paths = WorkspacePath(workspace)
        self._max_bytes = max_bytes
        self.definition = ToolDefinition(
            name="read_file",
            description="Read a UTF-8 text file from the workspace and return its contents.",
            parameters={
                "type": "object",
                "properties": {"path": _PATH_PROPERTY},
                "required": ["path"],
                "additionalProperties": False,
            },
        )

    async def run(self, arguments: Mapping[str, Any]) -> str:
        target = self._paths.resolve("read_file", arguments["path"])
        if not target.exists():
            raise ToolError("read_file: file not found")
        if not target.is_file():
            raise ToolError("read_file: path is not a file")
        try:
            with target.open("rb") as handle:
                data = handle.read(self._max_bytes + 1)
        except OSError as exc:
            raise ToolError("read_file: could not read the file") from exc
        if len(data) > self._max_bytes:
            raise ToolError(f"read_file: file is too large (limit {self._max_bytes} bytes)")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError("read_file: file is not valid UTF-8 text") from exc


class WriteFileTool:
    """Create or overwrite a UTF-8 text file in the Workspace, never under a protected root."""

    risk: RiskLevel = "high"

    def __init__(
        self,
        workspace: Path,
        protected_roots: Iterable[Path],
        max_bytes: int = MAX_FILE_BYTES,
    ) -> None:
        self._paths = WorkspacePath(workspace)
        self._protected = tuple(root.resolve() for root in protected_roots)
        self._max_bytes = max_bytes
        self.definition = ToolDefinition(
            name="write_file",
            description=(
                "Create or overwrite a UTF-8 text file in the workspace, "
                "creating parent directories."
            ),
            parameters={
                "type": "object",
                "properties": {"path": _PATH_PROPERTY, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        )

    async def run(self, arguments: Mapping[str, Any]) -> str:
        content: str = arguments["content"]
        data = content.encode("utf-8")
        if len(data) > self._max_bytes:
            raise ToolError(f"write_file: content is too large (limit {self._max_bytes} bytes)")
        target = self._paths.resolve("write_file", arguments["path"])
        if any(target.is_relative_to(root) for root in self._protected):
            raise ToolError("write_file: path is under a protected root")
        if target.is_dir():
            raise ToolError("write_file: path is a directory")
        _write_atomically(target, data)
        return f"wrote {len(data)} bytes to {arguments['path']}"


def _write_atomically(target: Path, data: bytes) -> None:
    """Write via a temp file in the same directory, then rename over the target."""
    temp_path: str | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_path = tempfile.mkstemp(dir=target.parent, prefix=".june-write-")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temp_path, target)
        temp_path = None
    except OSError as exc:
        raise ToolError("write_file: could not write the file") from exc
    finally:
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)
