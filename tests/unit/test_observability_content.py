import logging

import pytest

from june.observability import content_fields, get_logger

pytestmark = pytest.mark.unit

PROMPT = "tell me about my private medical history"


def test_info_logs_size_and_hash_but_not_text(log_output):
    stream, lines = log_output
    logger = get_logger("june.content.info")
    logger.setLevel(logging.INFO)

    logger.info("prompt sent", extra=content_fields(logger, "prompt", PROMPT))

    (line,) = lines()
    assert line["prompt_size"] == len(PROMPT)
    assert len(line["prompt_hash"]) == 16
    assert "prompt_text" not in line
    assert PROMPT not in stream.getvalue()


def test_debug_includes_full_text(log_output):
    _, lines = log_output
    logger = get_logger("june.content")

    logger.debug("tool result", extra=content_fields(logger, "tool_output", PROMPT))

    assert lines()[0]["tool_output_text"] == PROMPT


def test_debug_text_is_still_redacted(log_output):
    stream, _ = log_output
    logger = get_logger("june.content")

    logger.debug("p", extra=content_fields(logger, "prompt", "use key sk-abcdef1234567890XYZ"))

    assert "sk-abcdef1234567890XYZ" not in stream.getvalue()


def test_identical_content_hashes_identically_and_different_content_does_not():
    logger = get_logger("june.content.hash")

    a = content_fields(logger, "prompt", "same")
    b = content_fields(logger, "prompt", "same")
    c = content_fields(logger, "prompt", "different")

    assert a["prompt_hash"] == b["prompt_hash"]
    assert a["prompt_hash"] != c["prompt_hash"]
