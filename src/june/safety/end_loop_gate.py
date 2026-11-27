"""Gate 4: redacts and checks the final reply before it is returned."""

from june.observability.redaction import redact_text
from june.safety.adapters.length import LengthClassifier
from june.safety.decision import enforce
from june.safety.ports import Classifier, Judge
from june.shared.errors import DomainError

DEFAULT_MAX_REPLY_CHARS = 8000


class EndLoopGate:
    """Returns the reply with secrets redacted, or raises `SafetyDenied`.

    Fails open (ADR 0011): a broken checker leaves the redacted reply allowed.
    """

    def __init__(
        self,
        max_chars: int = DEFAULT_MAX_REPLY_CHARS,
        judge: Judge | None = None,
        classifier: Classifier | None = None,
    ) -> None:
        if max_chars < 1:
            raise DomainError("max_chars must be at least 1")
        self._classifier = classifier or LengthClassifier(max_chars)
        self._judge = judge

    async def check(self, reply: str) -> str:
        redacted = redact_text(reply)
        await enforce("end_loop", redacted, self._classifier, self._judge)
        return redacted
