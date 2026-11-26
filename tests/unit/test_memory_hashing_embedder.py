import math

import pytest

from june.memory import Embedder
from june.memory.adapters.hashing_embedder import HashingEmbedder
from june.shared import DomainError

pytestmark = pytest.mark.unit


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_same_text_gives_same_vector():
    embedder: Embedder = HashingEmbedder()

    first, second = await embedder.embed(["likes green tea", "likes green tea"])

    assert first == second


async def test_vector_has_declared_dimensions_and_unit_length():
    embedder = HashingEmbedder(dimensions=64)

    [vector] = await embedder.embed(["the quick brown fox"])

    assert len(vector) == embedder.info.dimensions == 64
    assert math.isclose(math.sqrt(dot(vector, vector)), 1.0)
    assert all(math.isfinite(x) for x in vector)


async def test_shared_words_score_higher_than_unrelated_text():
    embedder = HashingEmbedder()

    query, related, unrelated = await embedder.embed(
        ["favourite green tea", "drinks green tea daily", "mortgage interest rates"]
    )

    assert dot(query, related) > dot(query, unrelated)


async def test_case_and_whitespace_do_not_change_the_vector():
    embedder = HashingEmbedder()

    a, b = await embedder.embed(["Green  TEA", "green tea"])

    assert a == b


async def test_empty_batch_returns_empty_list():
    assert await HashingEmbedder().embed([]) == []


async def test_blank_text_gives_a_zero_vector():
    [vector] = await HashingEmbedder(dimensions=8).embed(["   "])

    assert vector == (0.0,) * 8


async def test_results_follow_input_order():
    embedder = HashingEmbedder()
    texts = ["alpha", "beta", "gamma"]

    batch = await embedder.embed(texts)
    singles = [(await embedder.embed([t]))[0] for t in texts]

    assert batch == singles


def test_info_names_the_embedder_and_its_version():
    info = HashingEmbedder(dimensions=32).info

    assert (info.name, info.version, info.dimensions) == ("hashing", "1", 32)


@pytest.mark.parametrize("dimensions", [0, -1])
def test_non_positive_dimensions_are_rejected(dimensions):
    with pytest.raises(DomainError):
        HashingEmbedder(dimensions=dimensions)
