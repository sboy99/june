"""Classifier for reply size."""

from june.safety.ports import Verdict


class LengthClassifier:
    """Denies empty or oversize text; text over half the limit is medium risk."""

    def __init__(self, max_chars: int) -> None:
        self._max_chars = max_chars

    def classify(self, text: str) -> Verdict:
        if not text.strip():
            return Verdict("deny", "low", "empty reply")
        if len(text) > self._max_chars:
            return Verdict("deny", "medium", "reply too long")
        if len(text) > self._max_chars // 2:
            return Verdict("allow", "medium", "long reply")
        return Verdict("allow", "low", "reply size ok")
