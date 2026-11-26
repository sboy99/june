"""`SkillStore` adapter: one JSON file per skill, confined to one directory."""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from june.memory.domain import Skill
from june.shared import DomainError, PermanentAdapterError

_SUFFIX = ".json"
_FORBIDDEN_CHARS = ("/", "\\", "\x00")
_PARENT = ".."
_SkillList = list[Skill]


def _checked_name(name: str) -> str:
    if not name.strip():
        raise PermanentAdapterError("skill name must not be blank")
    if any(char in name for char in _FORBIDDEN_CHARS) or _PARENT in name or name == ".":
        raise PermanentAdapterError("skill name must not contain path components")
    return name


def _encode(skill: Skill) -> str:
    return json.dumps(
        {
            "name": skill.name,
            "description": skill.description,
            "steps": list(skill.steps),
            "created_at": skill.created_at.isoformat(),
        },
        ensure_ascii=False,
    )


def _decode(raw: str, name: str) -> Skill:
    try:
        data = json.loads(raw)
        return Skill(
            name=data["name"],
            description=data["description"],
            steps=tuple(data["steps"]),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
    except (ValueError, KeyError, TypeError, DomainError) as exc:
        raise PermanentAdapterError(f"skill file for {name!r} is corrupt", cause=exc) from exc


class FileSkillStore:
    """Skills live as `<name>.json` under `root`; blocking file work runs in a worker thread."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    async def save(self, skill: Skill) -> None:
        path = self._path(skill.name)
        await asyncio.to_thread(self._write, path, _encode(skill))

    async def get(self, name: str) -> Skill | None:
        path = self._path(name)
        raw = await asyncio.to_thread(self._read, path)
        return None if raw is None else _decode(raw, name)

    async def list(self) -> _SkillList:
        return await asyncio.to_thread(self._read_all)

    async def delete(self, name: str) -> None:
        path = self._path(name)
        await asyncio.to_thread(self._remove, path)

    def _path(self, name: str) -> Path:
        path = self._root / f"{_checked_name(name)}{_SUFFIX}"
        if path.resolve().parent != self._root.resolve():
            raise PermanentAdapterError("skill name resolves outside the store")
        return path

    def _write(self, path: Path, text: str) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=self._root, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(text)
                os.replace(temp, path)
            except BaseException:
                Path(temp).unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise PermanentAdapterError("could not write skill file", cause=exc) from exc

    @staticmethod
    def _read(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise PermanentAdapterError("could not read skill file", cause=exc) from exc

    def _read_all(self) -> _SkillList:
        if not self._root.is_dir():
            return []
        skills = []
        for path in self._root.glob(f"*{_SUFFIX}"):
            raw = self._read(path)
            if raw is not None:
                skills.append(_decode(raw, path.stem))
        return sorted(skills, key=lambda skill: skill.name)

    def _remove(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise PermanentAdapterError("could not delete skill file", cause=exc) from exc
