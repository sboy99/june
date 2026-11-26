"""Gate policy table: what each Gate checks, may return, and logs.

Gates implement against this table. Failure defaults are fixed here
(see ADR 0011): every Gate fails closed except `end_loop`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from june.safety.ports import Decision, GateName
from june.shared.errors import DomainError

_LOGGED_FIELDS = ("gate", "decision", "risk", "reason", "subject_digest")


@dataclass(frozen=True)
class GatePolicy:
    """One row of the table."""

    gate: GateName
    checks: str
    allowed: tuple[Decision, ...]
    on_checker_error: Decision
    logged_fields: tuple[str, ...] = _LOGGED_FIELDS


GATE_POLICIES: Mapping[GateName, GatePolicy] = MappingProxyType(
    {
        "input": GatePolicy("input", "user message text", ("allow", "deny"), "deny"),
        "tool": GatePolicy(
            "tool", "tool call name and arguments", ("allow", "deny", "ask"), "deny"
        ),
        "memory_write": GatePolicy(
            "memory_write", "text about to be remembered", ("allow", "deny"), "deny"
        ),
        "end_loop": GatePolicy("end_loop", "final assistant answer", ("allow", "deny"), "allow"),
    }
)


def policy_for(gate: GateName) -> GatePolicy:
    """Return the policy row for `gate`; unknown names raise `DomainError`."""
    try:
        return GATE_POLICIES[gate]
    except KeyError:
        raise DomainError(f"unknown gate: {gate!r}") from None
