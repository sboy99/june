"""Offline, deterministic `Embedder`: hashes tokens into signed buckets."""

import hashlib
import math
from collections.abc import Sequence

from june.memory.domain.types import normalize_text
from june.memory.ports import EmbedderInfo, Vector

_NAME = "hashing"
_VERSION = "1"
_DEFAULT_DIMENSIONS = 256


def _bucket_and_sign(token: str, dimensions: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") % dimensions
    sign = 1.0 if digest[8] & 1 else -1.0
    return bucket, sign


def _embed_one(text: str, dimensions: int) -> Vector:
    counts = [0.0] * dimensions
    for token in normalize_text(text).split():
        bucket, sign = _bucket_and_sign(token, dimensions)
        counts[bucket] += sign
    norm = math.sqrt(sum(x * x for x in counts))
    if norm == 0.0:
        return tuple(counts)
    return tuple(x / norm for x in counts)


class HashingEmbedder:
    """No network, no model: the same text always gives the same unit-length vector."""

    def __init__(self, dimensions: int = _DEFAULT_DIMENSIONS) -> None:
        self._info = EmbedderInfo(name=_NAME, version=_VERSION, dimensions=dimensions)

    @property
    def info(self) -> EmbedderInfo:
        return self._info

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [_embed_one(text, self._info.dimensions) for text in texts]
