"""Classifiers for secrets and memory poisoning, and a composite."""

from june.observability.redaction import redact_text
from june.safety.adapters.patterns import INJECTION_RULES, PatternClassifier, PatternRule
from june.safety.ports import Classifier, Verdict


class SecretClassifier:
    """Denies text holding a secret-shaped substring (same patterns as log redaction)."""

    def classify(self, text: str) -> Verdict:
        if redact_text(text) != text:
            return Verdict("deny", "high", "text contains a secret")
        return Verdict("allow", "low", "no secret found")


class CompositeClassifier:
    """Returns the first non-allow verdict, else `allow`."""

    def __init__(self, *classifiers: Classifier) -> None:
        self._classifiers = classifiers

    def classify(self, text: str) -> Verdict:
        for classifier in self._classifiers:
            verdict = classifier.classify(text)
            if verdict.decision != "allow":
                return verdict
        return Verdict("allow", "low", "no check objected")


POISONING_RULES = (
    PatternRule(
        r"\b(from\s+now\s+on|henceforth|in\s+future)\b[^.\n]{0,40}"
        r"\b(you\s+(must|should|will|always|never)|always|never)\b",
        "high",
        "standing instruction planted in memory",
    ),
    PatternRule(
        r"\bnever\s+(tell|mention|reveal|show)\s+(the\s+)?(user|anyone)\b",
        "high",
        "concealment instruction planted in memory",
    ),
    PatternRule(
        r"\balways\s+(obey|trust|follow)\b", "high", "obedience instruction planted in memory"
    ),
)


def memory_write_classifier() -> Classifier:
    """Classifier for the memory-write Gate: secrets, poisoning and injection phrases."""
    return CompositeClassifier(
        SecretClassifier(),
        PatternClassifier(POISONING_RULES),
        PatternClassifier(INJECTION_RULES),
    )
