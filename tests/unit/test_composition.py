from pathlib import Path

import pytest
from pydantic import SecretStr

from june.composition import build_app, build_chat_model
from june.config import Settings
from june.llm.adapters.mock import MockChatModel
from june.llm.adapters.openai_compatible import OpenAICompatibleChatModel

pytestmark = pytest.mark.unit


@pytest.fixture
def persona(tmp_path: Path) -> Path:
    path = tmp_path / "SOUL.md"
    path.write_text("be kind", encoding="utf-8")
    return path


def test_mock_provider_builds_the_mock_model(persona):
    settings = Settings(persona_path=persona, llm_provider="mock")

    assert isinstance(build_chat_model(settings), MockChatModel)


def test_openai_provider_builds_the_openai_compatible_model(persona):
    settings = Settings(
        persona_path=persona,
        llm_provider="openai",
        llm_model="gpt-test",
        llm_api_key=SecretStr("sk-planted-secret-1234567890"),
        llm_base_url="http://localhost:1234/v1",
    )

    assert isinstance(build_chat_model(settings), OpenAICompatibleChatModel)


def test_app_holds_one_shared_chat_model(persona):
    app = build_app(Settings(persona_path=persona))

    assert isinstance(app.chat_model, MockChatModel)
    assert app.chat_model is app.chat_model
