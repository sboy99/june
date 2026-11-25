"""Composition root: the only place where the application is wired together."""

from dataclasses import dataclass

from june.config import Settings
from june.llm import ChatModel
from june.llm.adapters.mock import MockChatModel
from june.llm.adapters.openai_compatible import OpenAICompatibleChatModel
from june.shared import ConfigError, PersonaNotFound


@dataclass(frozen=True)
class App:
    """The wired application."""

    settings: Settings
    soul: str
    chat_model: ChatModel


def load_persona(settings: Settings) -> str:
    """Read the persona text from the configured path."""
    path = settings.persona_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PersonaNotFound(f"persona file not found or unreadable: {path}") from exc
    if not text.strip():
        raise PersonaNotFound(f"persona file is empty: {path}")
    return text


def build_chat_model(settings: Settings) -> ChatModel:
    """Build the chat model selected by `llm_provider`."""
    if settings.llm_provider == "mock":
        return MockChatModel(model=settings.llm_model)
    if settings.llm_api_key is None:
        raise ConfigError("invalid configuration: JUNE_LLM_API_KEY is required")
    return OpenAICompatibleChatModel(
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def build_app(settings: Settings) -> App:
    """Build the application from explicit settings; the chat model is built once and shared."""
    return App(
        settings=settings, soul=load_persona(settings), chat_model=build_chat_model(settings)
    )
