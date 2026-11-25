"""Identifier generation.

Ids are opaque strings: 32 lowercase hex characters (a UUID4 without dashes),
safe for URLs and file names. Callers that need determinism take an
`IdGenerator` and tests pass a fake.
"""

from typing import Protocol
from uuid import uuid4


class IdGenerator(Protocol):
    """Source of new ids."""

    def new_id(self) -> str: ...


class UuidGenerator:
    """Default `IdGenerator` backed by UUID4."""

    def new_id(self) -> str:
        return new_id()


def new_id() -> str:
    """Return a new unique, URL/file-safe id."""
    return uuid4().hex
