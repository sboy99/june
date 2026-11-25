from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from june.memory.domain import Episode, EpisodeStatus, Fact, Skill
from june.shared import DomainError

pytestmark = pytest.mark.unit

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_fact(**overrides):
    values = {"id": "f1", "user_id": "u1", "text": "Likes tea", "source": "user", "created_at": T0}
    return Fact(**{**values, **overrides})


def make_episode(**overrides):
    values = {"id": "e1", "user_id": "u1", "summary": "Talked about tea", "created_at": T0}
    return Episode(**{**values, **overrides})


def test_fact_defaults_to_active_without_profile_key():
    fact = make_fact()

    assert fact.profile_key is None
    assert fact.superseded_by is None
    assert fact.is_active


@pytest.mark.parametrize("text", ["", "   \n"])
def test_fact_rejects_blank_text(text):
    with pytest.raises(DomainError):
        make_fact(text=text)


def test_fact_rejects_empty_user_id():
    with pytest.raises(DomainError):
        make_fact(user_id=" ")


def test_fact_rejects_naive_datetime():
    with pytest.raises(DomainError):
        make_fact(created_at=datetime(2026, 1, 1))


def test_fact_is_immutable():
    with pytest.raises(FrozenInstanceError):
        make_fact().text = "other"  # type: ignore[misc]


def test_facts_are_equal_and_hashable_by_value():
    assert make_fact() == make_fact()
    assert len({make_fact(), make_fact()}) == 1


def test_mark_superseded_returns_new_inactive_fact():
    fact = make_fact()

    replaced = fact.mark_superseded("f2")

    assert replaced.superseded_by == "f2"
    assert not replaced.is_active
    assert fact.is_active


def test_episode_starts_pending_and_can_be_consolidated():
    episode = make_episode()

    done = episode.mark_consolidated()

    assert episode.status is EpisodeStatus.PENDING
    assert done.status is EpisodeStatus.CONSOLIDATED


def test_episode_rejects_blank_summary_and_naive_time():
    with pytest.raises(DomainError):
        make_episode(summary=" ")
    with pytest.raises(DomainError):
        make_episode(created_at=datetime(2026, 1, 1))


def test_episode_rejects_bad_status():
    with pytest.raises(DomainError):
        make_episode(status="done")


def test_episode_is_immutable():
    with pytest.raises(FrozenInstanceError):
        make_episode().summary = "x"  # type: ignore[misc]


def test_skill_holds_ordered_steps():
    skill = Skill(name="brew", description="Make tea", steps=("boil", "steep"), created_at=T0)

    assert skill.steps == ("boil", "steep")
    assert hash(skill) == hash(Skill("brew", "Make tea", ("boil", "steep"), T0))


def test_skill_rejects_blank_name_description_and_naive_time():
    with pytest.raises(DomainError):
        Skill(name=" ", description="d", steps=(), created_at=T0)
    with pytest.raises(DomainError):
        Skill(name="n", description=" ", steps=(), created_at=T0)
    with pytest.raises(DomainError):
        Skill(name="n", description="d", steps=(), created_at=datetime(2026, 1, 1))
