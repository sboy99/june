"""Safe logging of prompts and tool output: size and hash, full text only at DEBUG."""

import hashlib
import logging

HASH_LENGTH = 16


def content_fields(logger: logging.Logger, label: str, text: str) -> dict[str, object]:
    """Return log extras for sensitive content.

    `<label>_size` is the length in characters and `<label>_hash` the first 16 hex
    characters of the SHA-256 of the UTF-8 text. `<label>_text` is added only when
    the logger's effective level is DEBUG (and is still redacted on output).
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:HASH_LENGTH]
    fields: dict[str, object] = {f"{label}_size": len(text), f"{label}_hash": digest}
    if logger.isEnabledFor(logging.DEBUG):
        return {**fields, f"{label}_text": text}
    return fields
