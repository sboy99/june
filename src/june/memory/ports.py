"""Ports (interfaces) of the memory module."""

from typing import Protocol


class VectorIndex(Protocol):
    """Port: VectorIndex. Stub until the first adapter lands."""


class Embedder(Protocol):
    """Port: Embedder. Stub until the first adapter lands."""


class SkillStore(Protocol):
    """Port: SkillStore. Stub until the first adapter lands."""


class Summarizer(Protocol):
    """Port: Summarizer. Stub until the first adapter lands."""
