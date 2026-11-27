"""A `SkillStore` that asks a `WriteGuard` before saving."""

from june.memory.domain import Skill
from june.memory.ports import SkillStore, WriteGuard


class GuardedSkillStore:
    """Checks a Skill's name, description and steps before `save`; other calls pass through."""

    def __init__(self, inner: SkillStore, guard: WriteGuard) -> None:
        self._inner = inner
        self._guard = guard

    async def save(self, skill: Skill) -> None:
        await self._guard.check("\n".join([skill.name, skill.description, *skill.steps]))
        await self._inner.save(skill)

    async def get(self, name: str) -> Skill | None:
        return await self._inner.get(name)

    async def list(self) -> list[Skill]:
        return await self._inner.list()

    async def delete(self, name: str) -> None:
        await self._inner.delete(name)
