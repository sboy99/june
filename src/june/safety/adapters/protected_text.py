"""Classifier for text that orders a write to a protected path."""

import re

from june.safety.ports import Verdict
from june.safety.protected_paths import ProtectedPaths

_WRITE_VERBS = re.compile(
    r"\b(write|overwrite|edit|replace|delete|remove|modify|append|change|rewrite|rm)\b",
    re.IGNORECASE,
)


class ProtectedPathClassifier:
    """Denies text that mentions a protected path together with a write verb."""

    def __init__(self, protected: ProtectedPaths) -> None:
        names = protected.root_names
        folders = "|".join(re.escape(name) for name in names if "." not in name)
        files = "|".join(re.escape(name) for name in names if "." in name)
        parts = [rf"\b(?:{folders})[/\\]"] if folders else []
        if files:
            parts.append(rf"\b(?:{files})\b")
        self._mention = re.compile("|".join(parts), re.IGNORECASE)

    def classify(self, text: str) -> Verdict:
        if self._mention.search(text) and _WRITE_VERBS.search(text):
            return Verdict("deny", "high", "text orders a write to a protected path")
        return Verdict("allow", "low", "no protected write")
