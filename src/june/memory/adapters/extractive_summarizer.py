"""Offline, deterministic `Summarizer`: no model, no network.

`summarize` keeps the transcript as `role: text` lines cut to a length limit.
`distill` proposes no facts; a model-backed summarizer will.
"""

from collections.abc import Sequence

from june.memory.domain import Episode
from june.memory.ports import FactCandidate, TranscriptTurn
from june.shared import PermanentAdapterError

DEFAULT_MAX_CHARS = 1000


class ExtractiveSummarizer:
    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        self._max_chars = max_chars

    async def summarize(self, turns: Sequence[TranscriptTurn]) -> str:
        if not turns:
            raise PermanentAdapterError("nothing to summarize")
        text = "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
        return text[: self._max_chars]

    async def distill(self, episodes: Sequence[Episode]) -> list[FactCandidate]:
        return []
