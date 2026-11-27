"""A small JSON-schema subset validator for tool arguments.

Supports `required`, `properties` (with `type`, a name or a list of names, and
`enum`) and `additionalProperties: false`. An unsupported type name fails
validation (closed). Enum comparison keeps `True` distinct from `1`. Errors name
the field, never the value.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from june.shared.errors import ToolError

_TYPE_CHECKS: Mapping[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict, Mapping),
    "null": (type(None),),
}


def _matches_type(value: object, expected: str) -> bool:
    types = _TYPE_CHECKS.get(expected)
    if types is None:
        return False
    if isinstance(value, bool) and expected != "boolean":
        return False
    return isinstance(value, types)


def _matches_any_type(value: object, expected: str | list[str]) -> bool:
    names = [expected] if isinstance(expected, str) else expected
    return any(_matches_type(value, name) for name in names)


def _in_enum(value: object, allowed: Iterable[object]) -> bool:
    return any(
        value == option and isinstance(value, bool) == isinstance(option, bool)
        for option in allowed
    )


def validate_arguments(schema: Mapping[str, Any], arguments: Mapping[str, Any]) -> None:
    """Raise `ToolError` naming the first offending field."""
    properties: Mapping[str, Any] = schema.get("properties", {})
    for key in schema.get("required", ()):
        if key not in arguments:
            raise ToolError(f"invalid arguments: missing required field '{key}'")
    for key, value in arguments.items():
        rule = properties.get(key)
        if rule is None:
            if schema.get("additionalProperties") is False:
                raise ToolError(f"invalid arguments: unknown field '{key}'")
            continue
        expected = rule.get("type")
        if expected is not None and not _matches_any_type(value, expected):
            raise ToolError(f"invalid arguments: field '{key}' has an invalid type")
        if "enum" in rule and not _in_enum(value, rule["enum"]):
            raise ToolError(f"invalid arguments: field '{key}' is not an allowed value")
