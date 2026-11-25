import pytest

import june.shared as shared
from june.shared import clock, errors, ids

pytestmark = pytest.mark.unit


def _public_names(module) -> set[str]:
    return {
        name
        for name, value in vars(module).items()
        if not name.startswith("_") and getattr(value, "__module__", None) == module.__name__
    }


def test_all_names_resolve_to_attributes():
    assert all(hasattr(shared, name) for name in shared.__all__)


def test_all_names_every_public_symbol_of_the_shared_modules():
    expected = _public_names(errors) | _public_names(ids) | _public_names(clock)

    assert expected == set(shared.__all__)
