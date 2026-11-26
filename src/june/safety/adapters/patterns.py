"""Rule-based Classifier: ordered regex rules, first match wins."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from june.safety.ports import RiskLevel, Verdict


@dataclass(frozen=True)
class PatternRule:
    """One rule: a case-insensitive regex, the risk of a match and the reason."""

    pattern: str
    risk: RiskLevel
    reason: str


class PatternClassifier:
    """Denies on the first matching rule; allows at low risk when none match."""

    def __init__(self, rules: Sequence[PatternRule]) -> None:
        self._rules = tuple((re.compile(rule.pattern, re.IGNORECASE), rule) for rule in rules)

    def classify(self, text: str) -> Verdict:
        for compiled, rule in self._rules:
            if compiled.search(text):
                return Verdict("deny", rule.risk, rule.reason)
        return Verdict("allow", "low", "no rule matched")


INJECTION_RULES = (
    PatternRule(
        r"\b(ignore|disregard|forget)\s+(all\s+|any\s+)?(of\s+)?(your\s+|the\s+)?"
        r"(previous|prior|above|earlier)?\s*(instructions|rules|guidelines)",
        "high",
        "instruction override attempt",
    ),
    PatternRule(
        r"\b(reveal|show|print|repeat)\s+(me\s+)?(your\s+|the\s+)?(system\s+prompt|"
        r"hidden\s+instructions)",
        "high",
        "system prompt extraction attempt",
    ),
    PatternRule(r"\byou\s+are\s+now\b", "high", "persona override attempt"),
    PatternRule(r"\b(developer|god)\s+mode\b|\bDAN\b", "high", "jailbreak phrase"),
)


def injection_classifier() -> PatternClassifier:
    """Classifier for prompt-injection phrases."""
    return PatternClassifier(INJECTION_RULES)
