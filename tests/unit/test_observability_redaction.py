import pytest

from june.observability import REDACTED, get_logger

pytestmark = pytest.mark.unit

SECRET = "hunter2-SUPER-secret-value"
API_KEY = "sk-abcdef1234567890XYZ"


def test_planted_secret_in_message_is_absent_from_output(log_output):
    stream, _ = log_output

    get_logger("june.sec").info("calling with key %s", API_KEY)
    get_logger("june.sec").info(f"password={SECRET}")
    get_logger("june.sec").info("header Authorization: Bearer abc.def-123")

    out = stream.getvalue()
    assert API_KEY not in out
    assert SECRET not in out
    assert "abc.def-123" not in out
    assert REDACTED in out


@pytest.mark.parametrize("key", ["api_key", "Token", "PASSWORD", "client-secret", "authorization"])
def test_values_under_sensitive_keys_are_masked_whatever_they_contain(log_output, key):
    stream, lines = log_output

    get_logger("june.sec").info("x", extra={key: SECRET})

    assert SECRET not in stream.getvalue()
    assert lines()[0][key] == REDACTED


def test_secrets_in_nested_structures_are_masked(log_output):
    stream, _ = log_output

    get_logger("june.sec").info(
        "x",
        extra={
            "payload": {"headers": {"cookie": SECRET}, "items": [{"password": SECRET}, API_KEY]}
        },
    )

    out = stream.getvalue()
    assert SECRET not in out
    assert API_KEY not in out
    assert REDACTED in out


def test_secrets_in_exception_text_are_masked(log_output):
    stream, _ = log_output

    try:
        raise RuntimeError(f"failed with {API_KEY} and password={SECRET}")
    except RuntimeError:
        get_logger("june.sec").exception("boom")

    out = stream.getvalue()
    assert API_KEY not in out
    assert SECRET not in out
    assert REDACTED in out


def test_secrets_logged_at_debug_level_are_masked(log_output):
    stream, _ = log_output

    get_logger("june.sec").debug("key %s", API_KEY, extra={"token": SECRET})

    out = stream.getvalue()
    assert API_KEY not in out
    assert SECRET not in out


def test_redaction_does_not_mutate_the_callers_data(log_output):
    payload = {"password": SECRET}

    get_logger("june.sec").info("x", extra={"payload": payload})

    assert payload == {"password": SECRET}


def test_uninspectable_values_never_crash_or_leak(log_output):
    stream, lines = log_output

    class Hostile:
        def __str__(self) -> str:
            raise RuntimeError(SECRET)

        __repr__ = __str__

    get_logger("june.sec").info("x", extra={"thing": Hostile()})

    assert SECRET not in stream.getvalue()
    assert lines()[0]["thing"] == REDACTED


def test_innocent_text_is_left_alone(log_output):
    _, lines = log_output

    get_logger("june.sec").info("turn finished", extra={"steps": 4})

    assert lines()[0]["message"] == "turn finished"
    assert lines()[0]["steps"] == 4
