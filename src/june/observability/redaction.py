"""Secret redaction: masks by key name and by value pattern; never raises."""

import logging
import re

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = ("apikey", "token", "password", "secret", "authorization", "cookie")
_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret|authorization|cookie)\b\s*[=:]\s*\S+"),
)

_STANDARD_ATTRS = frozenset(
    logging.makeLogRecord({}).__dict__.keys() | {"message", "asctime", "taskName"}
)


def is_sensitive_key(key: object) -> bool:
    """Whether a field name marks its value as secret (case-insensitive substring)."""
    normalised = str(key).lower().replace("_", "").replace("-", "").replace(" ", "")
    return any(part in normalised for part in _SENSITIVE_KEY_PARTS)


def redact_text(text: str) -> str:
    """Mask secret-shaped substrings in free text."""
    for pattern in _VALUE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_value(value: object) -> object:
    """Return a redacted copy of a value, recursing into dicts, lists and tuples."""
    try:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, dict):
            return {
                key: REDACTED if is_sensitive_key(key) else redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list | tuple | set | frozenset):
            return [redact_value(item) for item in value]
        if value is None or isinstance(value, bool | int | float):
            return value
        return redact_text(str(value))
    except Exception:
        return REDACTED


class RedactionFilter(logging.Filter):
    """Handler filter masking secrets in the message, extra fields and exception text."""

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        clean = logging.makeLogRecord(record.__dict__)
        try:
            clean.msg = redact_text(record.getMessage())
        except Exception:
            clean.msg = REDACTED
        clean.args = None
        for key in record.__dict__.keys() - _STANDARD_ATTRS:
            clean.__dict__[key] = (
                REDACTED if is_sensitive_key(key) else redact_value(record.__dict__[key])
            )
        clean.exc_text = _redacted_exception(record)
        clean.exc_info = None
        clean.stack_info = redact_text(record.stack_info) if record.stack_info else None
        return clean


def _redacted_exception(record: logging.LogRecord) -> str | None:
    try:
        if record.exc_info:
            return redact_text(logging.Formatter().formatException(record.exc_info))
        return redact_text(record.exc_text) if record.exc_text else None
    except Exception:
        return REDACTED


def extra_fields(record: logging.LogRecord) -> dict[str, object]:
    """Return the caller-supplied extra fields of a record."""
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
