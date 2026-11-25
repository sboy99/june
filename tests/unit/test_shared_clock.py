from datetime import UTC, datetime, timedelta

import pytest

from june.shared import FixedClock, SystemClock

pytestmark = pytest.mark.unit

START = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_system_clock_returns_an_aware_utc_datetime():
    now = SystemClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_fixed_clock_returns_the_time_it_was_set_to():
    assert FixedClock(START).now() == START


def test_fixed_clock_can_be_advanced():
    clock = FixedClock(START)

    clock.advance(timedelta(minutes=5))

    assert clock.now() == START + timedelta(minutes=5)


def test_fixed_clock_rejects_naive_datetimes():
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 1, 1))
