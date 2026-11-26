"""Chat service: one user message in, one reply out, with memory around it.

Per message: recall memories, read the user's profile Facts and the Skills,
build the context, run the agent loop, save the answered Turn. Ending a
Session hands it to the Session closer, which works in the background.
"""

from dataclasses import dataclass

from june.conversation import Session, SessionStore, Turn
from june.memory import Fact, Recall, SkillStore, VectorIndex
from june.memory.ports import SearchFilter
from june.observability import new_trace_id, request_context
from june.runtime.context import ContextBuilder
from june.runtime.loop import AgentLoop, LoopStop
from june.runtime.session_closer import SessionCloser
from june.shared import Clock, DomainError, IdGenerator

RECALL_LIMIT = 5
MIN_RECALL_SIMILARITY = 0.1
_ACTIVE_FACTS = SearchFilter(kind="fact", active_only=True)
_SAVED_STOPS = frozenset({LoopStop.ANSWERED, LoopStop.TRUNCATED})


@dataclass(frozen=True, slots=True)
class ChatReply:
    """The result of one `chat` call; `session` is unchanged unless a Turn was saved."""

    reply: str
    session: Session
    stop: LoopStop
    error_code: str | None = None


class ChatService:
    """Starts Sessions, answers messages and ends Sessions."""

    def __init__(
        self,
        *,
        sessions: SessionStore,
        context_builder: ContextBuilder,
        agent_loop: AgentLoop,
        recall: Recall,
        index: VectorIndex,
        skills: SkillStore,
        clock: Clock,
        ids: IdGenerator,
        closer: SessionCloser,
    ) -> None:
        self._sessions = sessions
        self._context_builder = context_builder
        self._agent_loop = agent_loop
        self._recall = recall
        self._index = index
        self._skills = skills
        self._clock = clock
        self._ids = ids
        self._closer = closer

    async def start_session(self, user_id: str) -> Session:
        session = Session.start(user_id, self._ids.new_id(), self._clock.now())
        await self._sessions.save(session)
        return session

    async def chat(self, session: Session, message: str) -> ChatReply:
        if not message.strip():
            raise DomainError("message must not be blank")
        with request_context(
            trace_id=new_trace_id(self._ids), session_id=session.id, user_id=session.user_id
        ):
            return await self._answer(session, message)

    def end_session(self, session: Session) -> None:
        self._closer.end_session(session)

    async def drain(self) -> None:
        await self._closer.drain()

    async def _answer(self, session: Session, message: str) -> ChatReply:
        memories = await self._recall.execute(
            session.user_id, message, limit=RECALL_LIMIT, min_similarity=MIN_RECALL_SIMILARITY
        )
        entries = await self._index.list(session.user_id, _ACTIVE_FACTS)
        profile = [
            entry.item
            for entry in entries
            if isinstance(entry.item, Fact) and entry.item.profile_key
        ]
        prompt = self._context_builder.build(
            message,
            profile=profile,
            memories=memories,
            skills=await self._skills.list(),
            history=session.turns,
        )
        result = await self._agent_loop.run(prompt)
        if result.stop not in _SAVED_STOPS or not result.reply.strip():
            return ChatReply("", session, result.stop, result.error_code)
        updated = session.with_turn(Turn(message, result.reply, self._clock.now()))
        await self._sessions.save(updated)
        return ChatReply(result.reply, updated, result.stop)
