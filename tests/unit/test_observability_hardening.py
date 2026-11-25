import io
from datetime import datetime

import pytest

from june.observability import REDACTED, configure_logging, get_logger

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("key", ["timestamp", "level", "logger", "exception", "stack"])
def test_extra_fields_never_replace_core_fields(log_output, key):
    _, lines = log_output

    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("june.collide").exception("real message", extra={key: "spoofed"})

    (line,) = lines()
    assert line["logger"] == "june.collide"
    assert line["level"] == "ERROR"
    assert line["message"] == "real message"
    assert "ValueError: boom" in line["exception"]
    assert datetime.fromisoformat(line["timestamp"])
    assert line[f"extra_{key}"] == "spoofed"


def test_reconfiguring_does_not_close_the_callers_stream():
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)
    configure_logging("INFO", stream=stream)

    get_logger("june.keepopen").info("still writable")

    assert not stream.closed
    assert len(stream.getvalue().splitlines()) == 1


@pytest.mark.parametrize(
    "text",
    [
        '{"api_key": "abc123"}',
        "{'password': 'abc123'}",
        'password="correct horse battery"',
        "token: 'two words'",
    ],
)
def test_quoted_secrets_in_message_text_are_masked_whole(log_output, text):
    stream, lines = log_output

    get_logger("june.sec").info(text)

    out = stream.getvalue()
    for leaked in ("abc123", "horse", "battery", "words"):
        assert leaked not in out
    assert REDACTED in lines()[0]["message"]


def test_short_sk_style_keys_are_masked(log_output):
    stream, _ = log_output

    get_logger("june.sec").info("using sk-ab12cd now")

    assert "sk-ab12cd" not in stream.getvalue()


def test_sk_prefix_inside_ordinary_words_is_left_alone(log_output):
    _, lines = log_output

    get_logger("june.sec").info("ask-me and task-list")

    assert lines()[0]["message"] == "ask-me and task-list"
