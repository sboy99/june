import pytest

from june.composition import build_app
from june.config import Settings
from june.llm.adapters.mock import MockChatModel
from june.memory import FactCandidate
from june.runtime import LoopStop
from june.shared import DomainError, PermanentAdapterError

pytestmark = pytest.mark.e2e


@pytest.fixture
def app(tmp_path):
    persona = tmp_path / "SOUL.md"
    persona.write_text("be kind", encoding="utf-8")
    return build_app(Settings(persona_path=persona, data_dir=tmp_path / "data"))


def last_system_text(app) -> str:
    return app.chat_model.calls[-1].messages[0].content


async def test_a_message_gets_a_reply_and_is_saved_as_a_turn(app):
    session = await app.chat_service.start_session("u1")

    reply = await app.chat_service.chat(session, "hello there")

    stored = await app.session_store.get(session.id)
    assert (reply.reply, reply.stop) == ("echo: hello there", LoopStop.ANSWERED)
    assert [(t.user_message, t.reply) for t in stored.turns] == [
        ("hello there", "echo: hello there")
    ]


async def test_earlier_turns_are_in_the_next_prompt(app):
    session = await app.chat_service.start_session("u1")
    first = await app.chat_service.chat(session, "my cat is called Miso")

    await app.chat_service.chat(first.session, "what next")

    roles_and_text = [(m.role, m.content) for m in app.chat_model.calls[-1].messages[1:]]
    assert roles_and_text == [
        ("user", "my cat is called Miso"),
        ("assistant", "echo: my cat is called Miso"),
        ("user", "what next"),
    ]


async def test_an_earlier_session_is_recalled_as_untrusted_memory_in_a_later_one(app):
    first = await app.chat_service.start_session("u1")
    talked = await app.chat_service.chat(first, "my favourite colour is green")
    app.chat_service.end_session(talked.session)
    await app.chat_service.drain()

    second = await app.chat_service.start_session("u1")
    await app.chat_service.chat(second, "which colour is my favourite")

    system = last_system_text(app)
    assert "<untrusted_memory>" in system and "favourite colour is green" in system


async def test_another_users_memories_are_not_recalled(app):
    first = await app.chat_service.start_session("u1")
    talked = await app.chat_service.chat(first, "my favourite colour is green")
    app.chat_service.end_session(talked.session)
    await app.chat_service.drain()

    other = await app.chat_service.start_session("u2")
    await app.chat_service.chat(other, "which colour is my favourite")

    assert "untrusted_memory" not in last_system_text(app)


async def test_a_failed_run_returns_the_stop_reason_and_leaves_the_session_unchanged(app):
    failing = MockChatModel([PermanentAdapterError("bad key")])
    object.__setattr__(app.agent_loop, "_model", failing)
    session = await app.chat_service.start_session("u1")

    reply = await app.chat_service.chat(session, "hello")

    assert (reply.reply, reply.stop, reply.error_code) == (
        "",
        LoopStop.MODEL_ERROR,
        "adapter_permanent",
    )
    assert reply.session == session
    assert (await app.session_store.get(session.id)).turns == ()


async def test_a_blank_message_is_rejected_before_any_model_call(app):
    session = await app.chat_service.start_session("u1")

    with pytest.raises(DomainError):
        await app.chat_service.chat(session, "  ")

    assert app.chat_model.calls == ()


async def test_end_session_returns_before_the_episode_is_stored(app):
    session = await app.chat_service.start_session("u1")
    talked = await app.chat_service.chat(session, "remember the milk")

    app.chat_service.end_session(talked.session)
    assert await app.vector_index.list("u1") == []
    await app.chat_service.drain()

    assert len(await app.vector_index.list("u1")) == 1


async def test_consolidated_facts_with_a_profile_key_reach_the_prompt(app):
    class Scripted:
        async def summarize(self, turns):
            return "talked about names"

        async def distill(self, episodes):
            return [FactCandidate("the user is called Ada", "name")]

    closer = app.session_closer
    consolidate = closer._consolidate
    object.__setattr__(consolidate, "_summarizer", Scripted())
    closer._every_n = 1
    session = await app.chat_service.start_session("u1")
    talked = await app.chat_service.chat(session, "call me Ada")
    app.chat_service.end_session(talked.session)
    await app.chat_service.drain()

    await app.chat_service.chat(await app.chat_service.start_session("u1"), "hi")

    assert "- name: the user is called Ada" in last_system_text(app)
