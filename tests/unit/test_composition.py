from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from june.composition import build_app, build_chat_model, build_embedder
from june.config import Settings
from june.llm.adapters.mock import MockChatModel
from june.llm.adapters.openai_compatible import OpenAICompatibleChatModel
from june.memory.adapters.file_skill_store import FileSkillStore
from june.memory.adapters.hashing_embedder import HashingEmbedder
from june.memory.adapters.openai_embedder import OpenAICompatibleEmbedder
from june.memory.adapters.sqlite_index import SqliteVectorIndex
from june.shared import ConfigError

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


def test_app_holds_one_shared_chat_model(persona, tmp_path):
    app = build_app(Settings(persona_path=persona, data_dir=tmp_path))

    assert isinstance(app.chat_model, MockChatModel)
    assert app.chat_model is app.chat_model


def test_default_embedder_is_hashing_and_needs_no_key(persona, tmp_path):
    settings = Settings(persona_path=persona, data_dir=tmp_path)

    embedder = build_embedder(settings)

    assert isinstance(embedder, HashingEmbedder)
    assert embedder.info.dimensions == settings.embedder_dimensions


def test_openai_embedder_falls_back_to_the_llm_key_and_url(persona, tmp_path):
    settings = Settings(
        persona_path=persona,
        data_dir=tmp_path,
        embedder_provider="openai",
        llm_provider="openai",
        llm_model="gpt-test",
        llm_api_key=SecretStr("sk-planted-secret-1234567890"),
        llm_base_url="http://localhost:1234/v1",
        embedder_dimensions=16,
    )

    embedder = build_embedder(settings)

    assert isinstance(embedder, OpenAICompatibleEmbedder)
    assert embedder.info.dimensions == 16


def test_openai_embedder_without_any_key_is_invalid(persona, tmp_path):
    with pytest.raises(ValidationError) as caught:
        Settings(persona_path=persona, data_dir=tmp_path, embedder_provider="openai")

    assert "JUNE_EMBEDDER_API_KEY" in str(caught.value)


def test_app_wires_memory_under_the_data_dir(persona, tmp_path):
    data_dir = tmp_path / "nested" / "data"

    app = build_app(Settings(persona_path=persona, data_dir=data_dir))

    assert (data_dir / "memory.db").is_file()
    assert isinstance(app.vector_index, SqliteVectorIndex)
    assert isinstance(app.skill_store, FileSkillStore)
    assert isinstance(app.embedder, HashingEmbedder)


async def test_wired_memory_remembers_and_recalls(persona, tmp_path):
    app = build_app(Settings(persona_path=persona, data_dir=tmp_path))

    await app.remember_fact.execute("u1", "likes green tea", "chat")
    recalled = await app.recall.execute("u1", "green tea")
    await app.forget.everything("u1")

    assert [m.item.text for m in recalled] == ["likes green tea"]
    assert await app.recall.execute("u1", "green tea") == []


def test_unusable_data_dir_is_a_config_error(persona, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")

    with pytest.raises(ConfigError):
        build_app(Settings(persona_path=persona, data_dir=blocker / "data"))
