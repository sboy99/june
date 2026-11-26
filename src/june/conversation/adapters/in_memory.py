"""`SessionStore` adapter that keeps sessions in a dict, for tests and offline runs."""

from june.conversation.session import Session
from june.shared import PermanentAdapterError


def _require_id(value: str, label: str) -> None:
    if not value.strip():
        raise PermanentAdapterError(f"{label} must not be blank")


class InMemorySessionStore:
    """Stores immutable `Session` values by id."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def save(self, session: Session) -> None:
        self._sessions[session.id] = session

    async def get(self, session_id: str) -> Session | None:
        _require_id(session_id, "session id")
        return self._sessions.get(session_id)

    async def list_for_user(self, user_id: str) -> list[Session]:
        _require_id(user_id, "user id")
        owned = [s for s in self._sessions.values() if s.user_id == user_id]
        return sorted(owned, key=lambda s: (s.created_at, s.id))

    async def delete(self, session_id: str) -> None:
        _require_id(session_id, "session id")
        self._sessions.pop(session_id, None)
