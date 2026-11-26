from datetime import UTC, datetime

import pytest

from june.memory import SkillStore
from june.memory.adapters.file_skill_store import FileSkillStore
from june.memory.domain import Skill
from june.shared import PermanentAdapterError

pytestmark = pytest.mark.unit

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def skill(name="deploy", steps=("build", "ship")):
    return Skill(name=name, description=f"how to {name}", steps=steps, created_at=T0)


@pytest.fixture
def store(tmp_path) -> SkillStore:
    return FileSkillStore(tmp_path / "skills")


async def test_save_then_get_round_trips(store):
    await store.save(skill())

    assert await store.get("deploy") == skill()


async def test_get_missing_returns_none(store):
    assert await store.get("nope") is None


async def test_save_replaces_same_name(store):
    await store.save(skill(steps=("a",)))
    await store.save(skill(steps=("b", "c")))

    assert (await store.get("deploy")).steps == ("b", "c")
    assert len(await store.list()) == 1


async def test_list_is_ordered_by_name_and_empty_without_directory(store):
    assert await store.list() == []

    for name in ("zeta", "alpha", "mid"):
        await store.save(skill(name))

    assert [s.name for s in await store.list()] == ["alpha", "mid", "zeta"]


async def test_delete_removes_and_is_idempotent(store):
    await store.save(skill())

    await store.delete("deploy")
    await store.delete("deploy")

    assert await store.get("deploy") is None


async def test_unicode_and_dotted_names_are_allowed(store):
    for name in ("déploy", "v1.2 release"):
        await store.save(skill(name))
        assert (await store.get(name)).name == name


BAD_NAMES = ["..", ".", "a/b", "a\\b", "/etc/passwd", "../x", "x/..", "a\x00b", "a..b/c"]
BLANK_NAMES = ["", "  "]


@pytest.mark.parametrize("name", BAD_NAMES)
async def test_escaping_names_are_rejected_on_every_method(store, name):
    with pytest.raises(PermanentAdapterError):
        await store.get(name)
    with pytest.raises(PermanentAdapterError):
        await store.delete(name)
    with pytest.raises(PermanentAdapterError):
        await store.save(skill(name))


@pytest.mark.parametrize("name", BLANK_NAMES)
async def test_blank_names_are_rejected_on_get_and_delete(store, name):
    with pytest.raises(PermanentAdapterError):
        await store.get(name)
    with pytest.raises(PermanentAdapterError):
        await store.delete(name)


async def test_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "skills"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    (root / "evil.json").symlink_to(outside / "target.json")
    store = FileSkillStore(root)

    with pytest.raises(PermanentAdapterError):
        await store.save(skill("evil"))
    assert not (outside / "target.json").exists()


async def test_corrupt_file_is_a_permanent_error_without_content(store, tmp_path):
    await store.save(skill())
    (tmp_path / "skills" / "deploy.json").write_text("{not json SECRET-CONTENT")

    with pytest.raises(PermanentAdapterError) as caught:
        await store.get("deploy")

    assert "deploy" in str(caught.value)
    assert "SECRET-CONTENT" not in str(caught.value)


async def test_no_partial_files_are_left_behind(store, tmp_path):
    await store.save(skill())

    assert [p.name for p in (tmp_path / "skills").iterdir()] == ["deploy.json"]
