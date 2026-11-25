"""Request context: trace, session and user ids carried in context variables.

Context variables propagate into asyncio tasks created inside a binding block
and stay isolated between concurrent requests.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from june.shared import IdGenerator, UuidGenerator

_DEFAULT_IDS = UuidGenerator()
_trace_id: ContextVar[str | None] = ContextVar("june_trace_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("june_session_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("june_user_id", default=None)


@dataclass(frozen=True)
class RequestContext:
    """Snapshot of the ids bound to the current request."""

    trace_id: str | None
    session_id: str | None
    user_id: str | None


CONTEXT_FIELDS = ("trace_id", "session_id", "user_id")


def current_context() -> RequestContext:
    """Return the ids bound right now (all `None` outside a request)."""
    return RequestContext(_trace_id.get(), _session_id.get(), _user_id.get())


@contextmanager
def request_context(
    *,
    trace_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> Iterator[None]:
    """Bind the given ids for the duration of the block; unspecified ids keep their value."""
    tokens = [
        (var, var.set(value))
        for var, value in ((_trace_id, trace_id), (_session_id, session_id), (_user_id, user_id))
        if value is not None
    ]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def new_trace_id(ids: IdGenerator | None = None) -> str:
    """Return a fresh trace id from the given generator (default: shared UUID generator)."""
    return (ids or _DEFAULT_IDS).new_id()


class ContextFilter(logging.Filter):
    """Copy the current request context onto every record."""

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        with_context = logging.makeLogRecord(record.__dict__)
        context = current_context()
        with_context.trace_id = context.trace_id
        with_context.session_id = context.session_id
        with_context.user_id = context.user_id
        return with_context
