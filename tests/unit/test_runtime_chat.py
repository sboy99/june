import pytest

from june.composition import build_app
from june.config import Settings
from june.llm.adapters.mock import MockChatModel
from june.shared import PermanentAdapterError

pytestmark = pytest.mark.unit


async def test_log_lines_of_a_chat_call_carry_the_request_ids(tmp_path, log_output):
    persona = tmp_path / "SOUL.md"
    persona.write_text("be kind", encoding="utf-8")
    app = build_app(Settings(persona_path=persona, data_dir=tmp_path / "data"))
    object.__setattr__(app.agent_loop, "_model", MockChatModel([PermanentAdapterError("x")]))
    _, lines = log_output
    session = await app.chat_service.start_session("u1")

    await app.chat_service.chat(session, "hello")

    warned = [line for line in lines() if "model call failed" in str(line)]
    assert warned and warned[0]["session_id"] == session.id and warned[0]["user_id"] == "u1"
    assert warned[0]["trace_id"]
