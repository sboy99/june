import re

import pytest

from june.shared import IdGenerator, UuidGenerator, new_id

pytestmark = pytest.mark.unit

UNIQUENESS_SAMPLE_SIZE = 10_000
FORMAT_SAMPLE_SIZE = 100
ID_FORMAT = re.compile(r"[0-9a-f]{32}")


def test_ids_are_unique_across_many_calls():
    ids = {new_id() for _ in range(UNIQUENESS_SAMPLE_SIZE)}

    assert len(ids) == UNIQUENESS_SAMPLE_SIZE


def test_ids_are_32_lowercase_hex_characters():
    assert all(ID_FORMAT.fullmatch(new_id()) for _ in range(FORMAT_SAMPLE_SIZE))


def test_default_generator_yields_well_formed_unique_ids():
    gen = UuidGenerator()

    first, second = gen.new_id(), gen.new_id()

    assert first != second
    assert ID_FORMAT.fullmatch(first)


def test_an_injected_fake_id_source_is_honoured():
    class FakeIds:
        def new_id(self) -> str:
            return "fixed-id"

    def label(ids: IdGenerator) -> str:
        return f"session-{ids.new_id()}"

    assert label(FakeIds()) == "session-fixed-id"
