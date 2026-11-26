from datetime import UTC, datetime, timedelta, timezone

import pytest

from june.shared import DomainError, PermanentAdapterError
from june.shared.helpers import require_adapter_text, require_text, require_utc


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_require_text_rejects_blank_strings(value: str) -> None:
    with pytest.raises(DomainError, match="name must not be blank"):
        require_text(value, "name")


def test_require_text_rejects_non_strings() -> None:
    with pytest.raises(DomainError):
        require_text(None, "name")  # type: ignore[arg-type]


def test_require_text_accepts_content() -> None:
    require_text(" a ", "name")


def test_require_utc_rejects_naive_datetime() -> None:
    with pytest.raises(DomainError, match="when must be a timezone-aware UTC"):
        require_utc(datetime(2026, 1, 1), "when")


def test_require_utc_rejects_non_utc_offset() -> None:
    with pytest.raises(DomainError):
        require_utc(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2))), "when")


def test_require_utc_accepts_utc() -> None:
    require_utc(datetime(2026, 1, 1, tzinfo=UTC), "when")


def test_require_adapter_text_raises_permanent_adapter_error() -> None:
    with pytest.raises(PermanentAdapterError, match="id must not be blank"):
        require_adapter_text("  ", "id")
