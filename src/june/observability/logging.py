"""Structured JSON logging on top of stdlib `logging`."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

from june.observability.context import CONTEXT_FIELDS, ContextFilter
from june.observability.redaction import RedactionFilter, extra_fields
from june.shared import ConfigError

ROOT_LOGGER_NAME = "june"


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)


class JsonFormatter(logging.Formatter):
    """Render each record as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            payload[field] = getattr(record, field, None)
        payload.update({k: v for k, v in extra_fields(record).items() if k not in CONTEXT_FIELDS})
        if record.exc_text:
            payload["exception"] = record.exc_text
        elif record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        return json.dumps(payload, default=str)


class _JuneHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Marker subclass so reconfiguration can find and replace its own handler."""


def parse_level(level: str) -> int:
    """Convert a level name to its number, or raise `ConfigError`."""
    name = level.strip().upper()
    number = logging.getLevelNamesMapping().get(name)
    if number is None or number == logging.NOTSET:
        raise ConfigError(f"invalid log level: {level!r}")
    return number


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Configure the `june` logger tree: one JSON handler on stderr (or `stream`).

    Idempotent: a previous handler installed by this function is replaced.
    """
    number = parse_level(level)
    handler = _JuneHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ContextFilter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger(ROOT_LOGGER_NAME)
    for existing in [h for h in root.handlers if isinstance(h, _JuneHandler)]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(number)
    root.propagate = False
