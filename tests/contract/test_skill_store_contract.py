"""One contract suite run against every `SkillStore` adapter (SHIP-324)."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from june.memory import SkillStore
from june.memory.adapters.file_skill_store import FileSkillStore
from june.memory.domain import Skill
from june.shared import PermanentAdapterError

pytestmark = pytest.mark.contract

T0 = datetime(2026, 1, 1, tzinfo=UTC)
UNSAFE_NAMES = ["../escape", "a/b", "/abs", "a\\b", "bad\x00name", ".."]

FACTORIES: list[tuple[str, Callable[[Path], SkillStore]]] = [
    ("file", lambda tmp: FileSkillStore(tmp / "skills")),
]


def skill(name: str = "deploy", steps: tuple[str, ...] = ("build", "ship")) -> Skill:
    return Skill(name=name, description=f"how to {name}", steps=steps, created_at=T0)


@pytest.fixture(params=[pytest.param(f, id=name) for name, f in FACTORIES])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> SkillStore:
    return request.param(tmp_path)


async def test_save_then_get_round_trips(store):
    await store.save(skill())

    assert await store.get("deploy") == skill()


async def test_save_replaces_a_skill_with_the_same_name(store):
    await store.save(skill(steps=("a",)))
    await store.save(skill(steps=("b", "c")))

    assert (await store.get("deploy")).steps == ("b", "c")
    assert len(await store.list()) == 1


async def test_get_and_delete_of_a_missing_name_are_not_errors(store):
    assert await store.get("nope") is None
    await store.delete("nope")


async def test_delete_removes_the_skill(store):
    await store.save(skill())

    await store.delete("deploy")

    assert await store.get("deploy") is None


async def test_list_is_ordered_by_name(store):
    assert await store.list() == []
    for name in ("zeta", "alpha", "mid"):
        await store.save(skill(name))

    assert [s.name for s in await store.list()] == ["alpha", "mid", "zeta"]


@pytest.mark.parametrize("name", UNSAFE_NAMES)
async def test_unsafe_names_are_rejected_by_every_method(store, name):
    with pytest.raises(PermanentAdapterError):
        await store.get(name)
    with pytest.raises(PermanentAdapterError):
        await store.delete(name)
    with pytest.raises(PermanentAdapterError):
        await store.save(skill(name))
