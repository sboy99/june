from datetime import UTC, datetime, timedelta, timezone

import pytest

from june.conversation import Session, Turn
from june.shared import DomainError

pytestmark = pytest.mark.unit

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def turn(text: str = "hi", minutes: int = 0) -> Turn:
    return Turn(user_message=text, reply=f"re: {text}", created_at=T0 + timedelta(minutes=minutes))


def test_start_gives_an_empty_session_for_the_user():
    session = Session.start("u1", "s1", T0)

    assert (session.id, session.user_id, session.created_at, session.turns) == ("s1", "u1", T0, ())


def test_with_turn_returns_a_new_session_and_leaves_the_original_untouched():
    original = Session.start("u1", "s1", T0)

    updated = original.with_turn(turn("a")).with_turn(turn("b", 1))

    assert original.turns == ()
    assert [t.user_message for t in updated.turns] == ["a", "b"]


@pytest.mark.parametrize("user_id, session_id", [("", "s1"), ("  ", "s1"), ("u1", ""), ("u1", " ")])
def test_blank_ids_are_rejected(user_id, session_id):
    with pytest.raises(DomainError):
        Session.start(user_id, session_id, T0)


@pytest.mark.parametrize("message, reply", [("", "ok"), (" ", "ok"), ("hi", ""), ("hi", "\n")])
def test_blank_turn_text_is_rejected(message, reply):
    with pytest.raises(DomainError):
        Turn(user_message=message, reply=reply, created_at=T0)


@pytest.mark.parametrize(
    "when", [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))]
)
def test_non_utc_times_are_rejected(when):
    with pytest.raises(DomainError):
        Session.start("u1", "s1", when)
    with pytest.raises(DomainError):
        Turn(user_message="hi", reply="ok", created_at=when)


def test_session_turns_must_be_a_tuple_of_turns():
    with pytest.raises(DomainError):
        Session(id="s1", user_id="u1", created_at=T0, turns=[turn()])  # type: ignore[arg-type]
