"""`Embedder` adapter for any OpenAI-compatible embeddings endpoint."""

import math
from collections.abc import Sequence

import httpx2
import openai
from openai.types import Embedding

from june.memory.ports import EmbedderInfo, Vector
from june.shared import AdapterError, PermanentAdapterError, TransientAdapterError

_VERSION = "1"
_TRANSIENT_STATUSES = frozenset({408, 409, 429})
_SERVER_ERROR_FLOOR = 500


def _translate_error(exc: openai.OpenAIError) -> AdapterError:
    """Map an SDK exception to a june adapter error; never echo bodies or keys."""
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        text = f"openai embeddings request failed: {type(exc).__name__} (status {status})"
        if status in _TRANSIENT_STATUSES or status >= _SERVER_ERROR_FLOOR:
            return TransientAdapterError(text, cause=exc)
        return PermanentAdapterError(text, cause=exc)
    text = f"openai embeddings request failed: {type(exc).__name__}"
    if isinstance(exc, openai.APIConnectionError):
        return TransientAdapterError(text, cause=exc)
    return PermanentAdapterError(text, cause=exc)


class OpenAICompatibleEmbedder:
    """Talks to an OpenAI-compatible server; retries are the SDK's, bounded by `max_retries`."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        dimensions: int,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._info = EmbedderInfo(name=model, version=_VERSION, dimensions=dimensions)
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=timeout_seconds,
            max_retries=max_retries,
            http_client=http_client,
        )

    @property
    def info(self) -> EmbedderInfo:
        return self._info

    async def embed(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(
                model=self._info.name,
                input=list(texts),
                dimensions=self._info.dimensions,
            )
        except openai.OpenAIError as exc:
            raise _translate_error(exc) from exc
        return self._to_vectors(response.data, expected=len(texts))

    def _to_vectors(self, data: Sequence[Embedding], expected: int) -> list[Vector]:
        ordered = sorted(data, key=lambda item: item.index)
        if len(ordered) != expected:
            raise PermanentAdapterError("embeddings response has the wrong number of vectors")
        vectors: list[Vector] = []
        for item in ordered:
            vector = tuple(float(x) for x in item.embedding)
            if len(vector) != self._info.dimensions:
                raise PermanentAdapterError("embeddings response vector has the wrong length")
            if not all(math.isfinite(x) for x in vector):
                raise PermanentAdapterError("embeddings response contains non-finite values")
            vectors.append(vector)
        return vectors
