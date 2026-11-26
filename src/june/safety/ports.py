"""Ports of the safety module: decision vocabulary, `Classifier` and `Judge`.

All types are immutable. The ports take plain strings so `safety` stays
independent of its sibling modules (`llm`, `memory`, `runtime`).
"""

from dataclasses import dataclass
from typing import Literal, Protocol, get_args

from june.shared.errors import DomainError

Decision = Literal["allow", "deny", "ask"]
RiskLevel = Literal["low", "medium", "high"]
GateName = Literal["input", "tool", "memory_write", "end_loop"]


@dataclass(frozen=True)
class Verdict:
    """The outcome of one check: a Decision, its Risk level and a short reason."""

    decision: Decision
    risk: RiskLevel
    reason: str

    def __post_init__(self) -> None:
        if self.decision not in get_args(Decision):
            raise DomainError(f"unknown decision: {self.decision!r}")
        if self.risk not in get_args(RiskLevel):
            raise DomainError(f"unknown risk level: {self.risk!r}")
        if not self.reason.strip():
            raise DomainError("a verdict needs a reason")


class Classifier(Protocol):
    """Port: cheap, synchronous, rule-based check of a text. Does no I/O."""

    def classify(self, text: str) -> Verdict: ...


class Judge(Protocol):
    """Port: model-backed check; the composition root supplies the model."""

    async def judge(self, subject: str, question: str) -> Verdict: ...
