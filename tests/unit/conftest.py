import io
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from june.observability import configure_logging

LogLines = Callable[[], list[dict[str, Any]]]


@pytest.fixture
def log_output() -> Iterator[tuple[io.StringIO, LogLines]]:
    """Configure june logging into memory; yield the stream and a JSON-line parser."""
    stream = io.StringIO()
    configure_logging("DEBUG", stream=stream)

    def lines() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines()]

    yield stream, lines
    june_logger = logging.getLogger("june")
    june_logger.handlers.clear()
    june_logger.setLevel(logging.NOTSET)
