"""Protected paths: the roots the agent may never write to through tools."""

import posixpath
from collections.abc import Sequence
from pathlib import Path

DEFAULT_PROTECTED_ROOTS = ("persona", "skills")


class ProtectedPaths:
    """Knows the protected roots under a base directory. Pure string logic, no file access."""

    def __init__(
        self, base_dir: Path | str, roots: Sequence[str] = DEFAULT_PROTECTED_ROOTS
    ) -> None:
        self._base = posixpath.normpath(str(base_dir).replace("\\", "/"))
        self.root_names = tuple(roots)

    def root_of(self, path: str) -> str | None:
        """Return the protected root `path` falls under after normalisation, else None."""
        joined = posixpath.normpath(posixpath.join(self._base, path.replace("\\", "/")))
        for root in self.root_names:
            root_path = posixpath.join(self._base, root)
            if joined == root_path or joined.startswith(root_path + "/"):
                return root
        return None
