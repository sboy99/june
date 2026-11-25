import re

import pytest

from june.shared import IdGenerator, UuidGenerator, new_id

pytestmark = pytest.mark.unit

SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def test_ids_are_unique_across_many_calls():
    ids = {new_id() for _ in range(10_000)}

    assert len(ids) == 10_000


def test_ids_are_url_and_file_safe():
    assert all(SAFE.match(new_id()) for _ in range(100))


def test_default_generator_yields_safe_unique_ids():
    gen = UuidGenerator()

    first, second = gen.new_id(), gen.new_id()

    assert first != second
    assert SAFE.match(first)


def test_an_injected_fake_id_source_is_honoured():
    class FakeIds:
        def new_id(self) -> str:
            return "fixed-id"

    def label(ids: IdGenerator) -> str:
        return f"session-{ids.new_id()}"

    assert label(FakeIds()) == "session-fixed-id"
