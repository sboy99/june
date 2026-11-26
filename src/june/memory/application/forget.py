"""Use case that deletes memories."""

from collections.abc import Sequence

from june.memory.domain.helper import require_text
from june.memory.ports import VectorIndex


class Forget:
    """Delete memories by id or everything for one user; both are idempotent."""

    def __init__(self, index: VectorIndex) -> None:
        self._index = index

    async def by_ids(self, user_id: str, ids: Sequence[str]) -> None:
        require_text(user_id, "user id")
        if ids:
            await self._index.delete(user_id, ids)

    async def everything(self, user_id: str) -> None:
        require_text(user_id, "user id")
        await self._index.delete_user(user_id)
