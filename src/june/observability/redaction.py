"""Secret redaction: masks by key name and by value pattern; never raises."""

import logging
import re

from june.observability.record_fields import STANDARD_ATTRS

REDACTED = "[REDACTED]"

# Single source of truth; `_` marks an optional separator (`api_key`, `api-key`, `apikey`).
_SENSITIVE_WORDS = ("api_key", "token", "password", "secret", "authorization", "cookie")
_SENSITIVE_KEY_PARTS = tuple(word.replace("_", "") for word in _SENSITIVE_WORDS)
_SENSITIVE_WORD_REGEX = "|".join(word.replace("_", "[_-]?") for word in _SENSITIVE_WORDS)
_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}"),
    re.compile(rf"""(?ix)\b(?:{_SENSITIVE_WORD_REGEX})\b["']?\s*[=:]\s*(?:"[^"]*"|'[^']*'|\S+)"""),
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
        masked_record = logging.makeLogRecord(record.__dict__)
        try:
            masked_record.msg = redact_text(record.getMessage())
        except Exception:
            masked_record.msg = REDACTED
        masked_record.args = None
        for key in record.__dict__.keys() - STANDARD_ATTRS:
            masked_record.__dict__[key] = (
                REDACTED if is_sensitive_key(key) else redact_value(record.__dict__[key])
            )
        masked_record.exc_text = _masked_exception_text(record)
        masked_record.exc_info = None
        masked_record.stack_info = redact_text(record.stack_info) if record.stack_info else None
        return masked_record


def _masked_exception_text(record: logging.LogRecord) -> str | None:
    try:
        if record.exc_info:
            return redact_text(logging.Formatter().formatException(record.exc_info))
        return redact_text(record.exc_text) if record.exc_text else None
    except Exception:
        return REDACTED
