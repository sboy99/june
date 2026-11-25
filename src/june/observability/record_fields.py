"""Which attributes of a `LogRecord` are caller-supplied `extra` fields."""

import logging

STANDARD_ATTRS = frozenset(
    logging.makeLogRecord({}).__dict__.keys() | {"message", "asctime", "taskName"}
)


def extra_fields(record: logging.LogRecord) -> dict[str, object]:
    """Return the caller-supplied extra fields of a record."""
    return {k: v for k, v in record.__dict__.items() if k not in STANDARD_ATTRS}
