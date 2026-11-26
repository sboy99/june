"""Gate 1: scans user input and fetched content before the model sees it."""

from june.safety.decision import enforce
from june.safety.ports import Classifier, Judge

UNTRUSTED_TAG = "untrusted_content"


class InputGate:
    """Denies injection attempts and wraps fetched content as data."""

    def __init__(self, classifier: Classifier, judge: Judge | None = None) -> None:
        self._classifier = classifier
        self._judge = judge

    async def check(self, text: str) -> str:
        """Return `text` unchanged, or raise `SafetyDenied`."""
        await enforce("input", text, self._classifier, self._judge)
        return text

    async def check_untrusted(self, text: str, source: str) -> str:
        """Scan fetched content, then wrap it in an `untrusted_content` block."""
        await enforce("input", text, self._classifier, self._judge)
        safe = text.replace(f"</{UNTRUSTED_TAG}>", f"&lt;/{UNTRUSTED_TAG}>")
        safe_source = source.replace('"', "&quot;")
        return f'<{UNTRUSTED_TAG} source="{safe_source}">\n{safe}\n</{UNTRUSTED_TAG}>'
