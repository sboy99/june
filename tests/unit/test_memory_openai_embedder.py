import httpx2
import pytest

from june.memory import Embedder
from june.memory.adapters.openai_embedder import OpenAICompatibleEmbedder
from june.shared import PermanentAdapterError, TransientAdapterError
from openai_fakes import PLANTED_KEY, Server

pytestmark = pytest.mark.unit

DIMS = 3


def embeddings(*vectors, shuffle=False):
    data = [
        {"object": "embedding", "index": i, "embedding": list(v)} for i, v in enumerate(vectors)
    ]
    if shuffle:
        data.reverse()
    return {
        "object": "list",
        "model": "emb-test",
        "data": data,
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def make_embedder(server, **overrides):
    options = {
        "model": "emb-test",
        "api_key": PLANTED_KEY,
        "dimensions": DIMS,
        "base_url": "http://fake.local/v1",
        "max_retries": 0,
        "http_client": httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    }
    return OpenAICompatibleEmbedder(**{**options, **overrides})


async def test_vectors_are_returned_in_input_order():
    server = Server(embeddings([1, 0, 0], [0, 1, 0]))
    embedder: Embedder = make_embedder(server)

    vectors = await embedder.embed(["a", "b"])

    assert vectors == [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    assert server.last_body["input"] == ["a", "b"]
    assert server.last_body["model"] == "emb-test"


async def test_response_is_reordered_by_index():
    server = Server(embeddings([1, 0, 0], [0, 1, 0], shuffle=True))

    vectors = await make_embedder(server).embed(["a", "b"])

    assert vectors == [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]


async def test_empty_batch_makes_no_request():
    server = Server(embeddings())

    assert await make_embedder(server).embed([]) == []
    assert server.requests == []


def test_info_uses_model_name_and_dimensions():
    info = make_embedder(Server(embeddings())).info

    assert (info.name, info.version, info.dimensions) == ("emb-test", "1", DIMS)


@pytest.mark.parametrize(
    "body",
    [
        embeddings([1, 0, 0]),  # too few vectors
        embeddings([1, 0], [0, 1]),  # wrong length
    ],
)
async def test_malformed_response_is_permanent(body):
    with pytest.raises(PermanentAdapterError):
        await make_embedder(Server(body)).embed(["a", "b"])


@pytest.mark.parametrize("status", [408, 409, 429, 500, 503])
async def test_retryable_statuses_are_transient(status):
    server = Server((status, {"error": {"message": "boom", "type": "x"}}))

    with pytest.raises(TransientAdapterError):
        await make_embedder(server).embed(["a"])


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_other_statuses_are_permanent(status):
    server = Server((status, {"error": {"message": "nope", "type": "x"}}))

    with pytest.raises(PermanentAdapterError):
        await make_embedder(server).embed(["a"])


async def test_connection_failure_is_transient():
    server = Server(httpx2.ConnectError("down"))

    with pytest.raises(TransientAdapterError):
        await make_embedder(server).embed(["a"])


async def test_errors_never_leak_key_or_input():
    server = Server((401, {"error": {"message": f"bad key {PLANTED_KEY}", "type": "x"}}))

    with pytest.raises(PermanentAdapterError) as caught:
        await make_embedder(server).embed(["secret input text"])

    assert PLANTED_KEY not in str(caught.value)
    assert "secret input text" not in str(caught.value)
