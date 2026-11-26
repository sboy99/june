"""One contract suite run against every `Embedder` adapter (SHIP-324)."""

import math
from collections.abc import Callable
from dataclasses import dataclass

import httpx2
import pytest

from june.memory import Embedder
from june.memory.adapters.hashing_embedder import HashingEmbedder
from june.memory.adapters.openai_embedder import OpenAICompatibleEmbedder
from june.shared import PermanentAdapterError, TransientAdapterError
from openai_fakes import PLANTED_KEY, Server

pytestmark = pytest.mark.contract

DIMS = 8


def _embeddings_response(texts_count: int) -> dict:
    return {
        "object": "list",
        "model": "emb-test",
        "data": [
            {
                "object": "embedding",
                "index": i,
                "embedding": [float(i + 1)] + [0.5] * (DIMS - 1),
            }
            for i in range(texts_count)
        ],
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


class EchoServer(Server):
    """Fake endpoint that answers with one vector per requested input."""

    def __init__(self) -> None:
        super().__init__({})

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(200, json=_embeddings_response(len(self.last_body["input"])))


@dataclass(frozen=True)
class Harness:
    name: str
    factory: Callable[[], Embedder]
    failing: Callable[[int], Embedder] | None = None

    def build(self) -> Embedder:
        return self.factory()


def _openai(server: Callable[[httpx2.Request], httpx2.Response]) -> Embedder:
    return OpenAICompatibleEmbedder(
        model="emb-test",
        api_key=PLANTED_KEY,
        dimensions=DIMS,
        base_url="http://fake.local/v1",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    )


def _openai_failing(status: int) -> Embedder:
    return _openai(Server((status, {"error": {"message": PLANTED_KEY}})))


HARNESSES = [
    pytest.param(Harness("hashing", lambda: HashingEmbedder(DIMS)), id="hashing"),
    pytest.param(
        Harness("openai-fake", lambda: _openai(EchoServer()), failing=_openai_failing),
        id="openai-fake",
    ),
]


@pytest.fixture(params=HARNESSES)
def harness(request: pytest.FixtureRequest) -> Harness:
    return request.param


async def test_one_vector_per_text_in_input_order(harness):
    embedder = harness.build()

    vectors = await embedder.embed(["a", "b", "c"])

    assert len(vectors) == 3
    if harness.name == "hashing":
        assert vectors[0] == (await embedder.embed(["a"]))[0]
        assert vectors[2] == (await embedder.embed(["c"]))[0]


async def test_vectors_have_declared_dimensions_and_are_finite(harness):
    embedder = harness.build()

    vectors = await embedder.embed(["hello", "world"])

    assert all(len(v) == embedder.info.dimensions == DIMS for v in vectors)
    assert all(math.isfinite(x) for v in vectors for x in v)


async def test_same_text_gives_the_same_vector(harness):
    embedder = harness.build()

    [first] = await embedder.embed(["repeat me"])
    [second] = await embedder.embed(["repeat me"])

    assert first == second


async def test_empty_batch_returns_empty_list(harness):
    assert await harness.build().embed([]) == []


async def test_blank_text_is_allowed(harness):
    [vector] = await harness.build().embed(["   "])

    assert len(vector) == DIMS


async def test_info_names_the_embedder(harness):
    info = harness.build().info

    assert info.name.strip() and info.version.strip()
    assert info.dimensions == DIMS


@pytest.mark.parametrize(
    ("status", "error"), [(503, TransientAdapterError), (401, PermanentAdapterError)]
)
async def test_failures_are_translated_without_leaking_the_key(harness, status, error):
    if harness.failing is None:
        pytest.skip(f"{harness.name} cannot fail")

    with pytest.raises(error) as raised:
        await harness.failing(status).embed(["x"])

    assert PLANTED_KEY not in str(raised.value)
