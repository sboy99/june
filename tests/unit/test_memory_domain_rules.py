from datetime import UTC, datetime, timedelta

import pytest

from june.memory.domain import (
    Episode,
    EpisodeStatus,
    Fact,
    RetentionPolicy,
    find_duplicate,
    is_episode_expired,
    is_fact_purgeable,
    recency_decay,
    supersede,
)
from june.shared import DomainError

pytestmark = pytest.mark.unit

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def fact(id="f1", user_id="u1", text="Likes tea", profile_key=None, superseded_by=None):
    return Fact(
        id=id,
        user_id=user_id,
        text=text,
        source="user",
        created_at=T0,
        profile_key=profile_key,
        superseded_by=superseded_by,
    )


def episode(status=EpisodeStatus.PENDING, created_at=T0):
    return Episode(id="e1", user_id="u1", summary="s", created_at=created_at, status=status)


# supersede


def test_supersede_replaces_active_fact_with_same_profile_key():
    old = fact("f1", profile_key="timezone", text="UTC")
    new = fact("f2", profile_key="timezone", text="CET")

    replaced = supersede([old], new)

    assert replaced == (old.mark_superseded("f2"),)


def test_supersede_normalizes_key_case_and_whitespace():
    old = fact("f1", profile_key="Timezone")
    new = fact("f2", profile_key=" timezone ")

    assert len(supersede([old], new)) == 1


def test_supersede_ignores_facts_without_key():
    old = fact("f1", profile_key="name")

    assert supersede([old], fact("f2")) == ()
    assert supersede([fact("f1")], fact("f2", profile_key="name")) == ()


def test_supersede_ignores_other_users():
    old = fact("f1", user_id="u2", profile_key="name")

    assert supersede([old], fact("f2", profile_key="name")) == ()


def test_supersede_ignores_already_superseded_and_other_keys():
    gone = fact("f1", profile_key="name", superseded_by="f0")
    other = fact("f3", profile_key="city")

    assert supersede([gone, other], fact("f2", profile_key="name")) == ()


def test_supersede_does_not_touch_input_facts():
    old = fact("f1", profile_key="name")

    supersede([old], fact("f2", profile_key="name"))

    assert old.is_active


# dedupe


def test_find_duplicate_matches_ignoring_case_and_whitespace():
    existing = fact("f1", text="Likes   Green tea")

    assert find_duplicate([existing], fact("f2", text="  likes green TEA ")) == existing


def test_find_duplicate_returns_none_when_text_differs():
    assert find_duplicate([fact("f1", text="a")], fact("f2", text="b")) is None


def test_find_duplicate_ignores_other_users_and_superseded():
    other_user = fact("f1", user_id="u2")
    gone = fact("f3", superseded_by="f9")

    assert find_duplicate([other_user, gone], fact("f2")) is None


# decay


def test_decay_is_one_at_age_zero():
    assert recency_decay(T0, T0) == 1.0


def test_decay_halves_after_one_half_life():
    assert recency_decay(T0, T0 + 7 * DAY, half_life=7 * DAY) == pytest.approx(0.5)


def test_decay_falls_monotonically_and_stays_positive():
    values = [recency_decay(T0, T0 + n * DAY) for n in range(0, 400, 40)]

    assert values == sorted(values, reverse=True)
    assert all(0 < v <= 1 for v in values)


def test_decay_clamps_future_dated_memory():
    assert recency_decay(T0 + DAY, T0) == 1.0


def test_decay_rejects_non_positive_half_life():
    with pytest.raises(DomainError):
        recency_decay(T0, T0, half_life=timedelta(0))
    with pytest.raises(DomainError):
        recency_decay(T0, T0, half_life=-DAY)


def test_decay_never_underflows_to_zero():
    assert 0 < recency_decay(T0, T0 + 100_000 * DAY, half_life=DAY) <= 1


def test_supersede_excludes_the_new_fact_itself():
    new = fact(id="f2", profile_key="name")

    assert supersede([fact(id="f1", profile_key="name"), new], new) == (
        fact(id="f1", profile_key="name", superseded_by="f2"),
    )


@pytest.mark.parametrize("field", ["episode_retention", "superseded_grace"])
def test_retention_policy_rejects_negative_durations(field):
    with pytest.raises(DomainError):
        RetentionPolicy(**{field: -DAY})


# retention

POLICY = RetentionPolicy(episode_retention=30 * DAY, superseded_grace=10 * DAY)


def test_consolidated_episode_expires_after_retention_boundary():
    done = episode(EpisodeStatus.CONSOLIDATED)

    assert not is_episode_expired(done, T0 + 30 * DAY, POLICY)
    assert is_episode_expired(done, T0 + 30 * DAY + timedelta(seconds=1), POLICY)


def test_pending_episode_never_expires():
    assert not is_episode_expired(episode(), T0 + 3650 * DAY, POLICY)


def test_active_fact_is_never_purgeable():
    assert not is_fact_purgeable(fact(), T0, T0 + 3650 * DAY, POLICY)


def test_superseded_fact_purgeable_after_grace():
    old = fact(superseded_by="f2")

    assert not is_fact_purgeable(old, T0, T0 + 10 * DAY, POLICY)
    assert is_fact_purgeable(old, T0, T0 + 11 * DAY, POLICY)


def test_default_policy_is_usable():
    done = episode(EpisodeStatus.CONSOLIDATED)

    assert is_episode_expired(done, T0 + 3650 * DAY, RetentionPolicy())
