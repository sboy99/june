"""Protected paths: the roots the agent may never write to through tools."""

import posixpath
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

DEFAULT_PROTECTED_ROOTS = ("persona", "skills")


class ProtectedPaths:
    """Knows the protected roots under a base directory. Pure string logic, no file access."""

    def __init__(
        self, base_dir: Path | str, roots: Sequence[Path | str] = DEFAULT_PROTECTED_ROOTS
    ) -> None:
        self._base = posixpath.normpath(str(base_dir).replace("\\", "/"))
        self._roots = tuple(str(root).replace("\\", "/") for root in roots)
        self.root_names = tuple(PurePosixPath(root).name for root in self._roots)

    def root_of(self, path: str) -> str | None:
        """Return the protected root `path` falls under after normalisation, else None."""
        joined = posixpath.normpath(posixpath.join(self._base, path.replace("\\", "/")))
        for root, name in zip(self._roots, self.root_names, strict=True):
            root_path = posixpath.normpath(posixpath.join(self._base, root))
            if joined == root_path or joined.startswith(root_path + "/"):
                return name
        return None
