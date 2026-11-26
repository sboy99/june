"""Gate 3: checks text before it is stored as a Fact, Episode or Skill."""

from june.safety.decision import enforce
from june.safety.ports import Classifier, Judge


class MemoryWriteGate:
    """Raises `SafetyDenied` for secrets and poisoning attempts."""

    def __init__(self, classifier: Classifier, judge: Judge | None = None) -> None:
        self._classifier = classifier
        self._judge = judge

    async def check(self, text: str) -> None:
        await enforce("memory_write", text, self._classifier, self._judge)
