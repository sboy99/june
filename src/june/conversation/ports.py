"""Ports (interfaces) of the conversation module."""

from typing import Protocol

from june.conversation.session import Session


class SessionStore(Protocol):
    """Port: persists sessions with their turns; `Session.id` is the identity.

    Contract every adapter must meet:

    - `save` creates a session or replaces the one with the same id, turns included.
    - `get` of a missing id returns None; `delete` of a missing id is not an error.
    - `list_for_user` returns only that user's sessions, oldest first (ties by id).
    - Turn order is preserved exactly.
    - A blank id raises `PermanentAdapterError` on every method.
    - Only `TransientAdapterError` and `PermanentAdapterError` (from
      `june.shared`) escape; error text never contains secrets.
    """

    async def save(self, session: Session) -> None: ...

    async def get(self, session_id: str) -> Session | None: ...

    async def list_for_user(self, user_id: str) -> list[Session]: ...

    async def delete(self, session_id: str) -> None: ...
