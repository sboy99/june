"""Composition root: the only place where the application is wired together."""

from dataclasses import dataclass

from june.config import Settings
from june.conversation import SessionStore
from june.conversation.adapters.sqlite import SqliteSessionStore
from june.llm import ChatModel
from june.llm.adapters.mock import MockChatModel
from june.llm.adapters.openai_compatible import OpenAICompatibleChatModel
from june.memory import (
    Embedder,
    Forget,
    Recall,
    RememberEpisode,
    RememberFact,
    SkillStore,
    VectorIndex,
)
from june.memory.adapters.file_skill_store import FileSkillStore
from june.memory.adapters.hashing_embedder import HashingEmbedder
from june.memory.adapters.openai_embedder import OpenAICompatibleEmbedder
from june.memory.adapters.sqlite_index import SqliteVectorIndex
from june.runtime import ContextBuilder
from june.shared import ConfigError, PersonaNotFound, SystemClock, UuidGenerator

MEMORY_DB_FILE = "memory.db"
SKILLS_DIR = "skills"
SESSIONS_DB_FILE = "sessions.db"


@dataclass(frozen=True)
class App:
    """The wired application."""

    settings: Settings
    soul: str
    chat_model: ChatModel
    embedder: Embedder
    vector_index: VectorIndex
    skill_store: SkillStore
    remember_fact: RememberFact
    remember_episode: RememberEpisode
    recall: Recall
    forget: Forget
    session_store: SessionStore
    context_builder: ContextBuilder


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


def build_embedder(settings: Settings) -> Embedder:
    """Build the embedder selected by `embedder_provider`."""
    if settings.embedder_provider == "hashing":
        return HashingEmbedder(settings.embedder_dimensions)
    api_key = settings.effective_embedder_api_key
    if api_key is None:
        raise ConfigError("invalid configuration: JUNE_EMBEDDER_API_KEY is required")
    return OpenAICompatibleEmbedder(
        model=settings.embedder_model,
        api_key=api_key.get_secret_value(),
        dimensions=settings.embedder_dimensions,
        base_url=settings.effective_embedder_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def build_app(settings: Settings) -> App:
    """Build the application from explicit settings; each part is built once and shared."""
    soul = load_persona(settings)
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"data directory is not usable: {settings.data_dir}") from exc
    embedder = build_embedder(settings)
    index = SqliteVectorIndex(settings.data_dir / MEMORY_DB_FILE)
    clock, ids = SystemClock(), UuidGenerator()
    return App(
        settings=settings,
        soul=soul,
        chat_model=build_chat_model(settings),
        embedder=embedder,
        vector_index=index,
        skill_store=FileSkillStore(settings.data_dir / SKILLS_DIR),
        remember_fact=RememberFact(index, embedder, clock, ids),
        remember_episode=RememberEpisode(index, embedder, clock, ids),
        recall=Recall(index, embedder, clock),
        forget=Forget(index),
        session_store=SqliteSessionStore(settings.data_dir / SESSIONS_DB_FILE),
        context_builder=ContextBuilder(soul),
    )
