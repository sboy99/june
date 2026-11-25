import io
import json
from datetime import datetime

import pytest

from june.observability import configure_logging, get_logger
from june.shared import ConfigError

pytestmark = pytest.mark.unit


def test_each_line_is_a_json_object_with_core_and_context_fields(log_output):
    _, lines = log_output

    get_logger("june.test").info("hello")

    (line,) = lines()
    assert line["level"] == "INFO"
    assert line["logger"] == "june.test"
    assert line["message"] == "hello"
    assert datetime.fromisoformat(line["timestamp"]).utcoffset().total_seconds() == 0
    assert line["trace_id"] is None
    assert line["session_id"] is None
    assert line["user_id"] is None


def test_extra_fields_appear_as_json_keys(log_output):
    _, lines = log_output

    get_logger("june.test").info("hello", extra={"step": 3, "tool": "search"})

    (line,) = lines()
    assert line["step"] == 3
    assert line["tool"] == "search"


def test_exception_details_are_included_on_the_same_line(log_output):
    _, lines = log_output

    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("june.test").exception("failed")

    (line,) = lines()
    assert "ValueError: boom" in line["exception"]


def test_unserialisable_extra_values_do_not_break_logging(log_output):
    _, lines = log_output

    get_logger("june.test").info("hello", extra={"obj": object()})

    assert len(lines()) == 1


def test_log_level_filters_lines_below_it():
    stream = io.StringIO()
    configure_logging("WARNING", stream=stream)
    logger = get_logger("june.level")

    logger.info("quiet")
    logger.warning("loud")

    messages = [json.loads(line)["message"] for line in stream.getvalue().splitlines()]
    assert messages == ["loud"]


def test_configuring_twice_yields_one_line_per_call():
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)
    configure_logging("INFO", stream=stream)

    get_logger("june.twice").info("once")

    assert len(stream.getvalue().splitlines()) == 1


@pytest.mark.parametrize("level", ["LOUD", "", "NOTSET", "15"])
def test_invalid_level_raises_config_error(level):
    with pytest.raises(ConfigError):
        configure_logging(level, stream=io.StringIO())


def test_level_name_is_case_insensitive():
    stream = io.StringIO()
    configure_logging("debug", stream=stream)

    get_logger("june.case").debug("visible")

    assert len(stream.getvalue().splitlines()) == 1
