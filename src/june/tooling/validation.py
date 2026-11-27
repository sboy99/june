"""A small JSON-schema subset validator for tool arguments.

Supports `required`, `properties` (with `type` and `enum`) and
`additionalProperties: false`. Errors name the field, never the value.
"""

from collections.abc import Mapping
from typing import Any

from june.shared.errors import ToolError

_TYPE_CHECKS: Mapping[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict, Mapping),
}


def _matches_type(value: object, expected: str) -> bool:
    types = _TYPE_CHECKS.get(expected)
    if types is None:
        return True
    if isinstance(value, bool) and expected != "boolean":
        return False
    return isinstance(value, types)


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
        if isinstance(expected, str) and not _matches_type(value, expected):
            raise ToolError(f"invalid arguments: field '{key}' must be {expected}")
        if "enum" in rule and value not in rule["enum"]:
            raise ToolError(f"invalid arguments: field '{key}' is not an allowed value")
