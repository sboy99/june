"""Composition root: the only place where the application is wired together."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from june.config import Settings
from june.conversation import SessionStore
from june.conversation.adapters.sqlite import SqliteSessionStore
from june.llm import ChatModel
from june.llm.adapters.mock import MockChatModel
from june.llm.adapters.openai_compatible import OpenAICompatibleChatModel
from june.memory import (
    Consolidate,
    Embedder,
    Forget,
    GuardedSkillStore,
    Recall,
    RememberConversation,
    RememberEpisode,
    RememberFact,
    SkillStore,
    VectorIndex,
)
from june.memory.adapters.extractive_summarizer import ExtractiveSummarizer
from june.memory.adapters.file_skill_store import FileSkillStore
from june.memory.adapters.hashing_embedder import HashingEmbedder
from june.memory.adapters.openai_embedder import OpenAICompatibleEmbedder
from june.memory.adapters.sqlite_index import SqliteVectorIndex
from june.runtime import (
    AgentLoop,
    ChatService,
    Compactor,
    ContextBuilder,
    GatedToolRunner,
    SessionCloser,
    ToolRunner,
)
from june.safety import (
    EndLoopGate,
    InputGate,
    MemoryWriteGate,
    ProtectedPaths,
    ToolGate,
    injection_classifier,
    memory_write_classifier,
)
from june.shared import ConfigError, PersonaNotFound, SystemClock, UuidGenerator
from june.tool_runner import RegistryToolRunner
from june.tooling import Tool, ToolRegistry
from june.tooling.adapters.files import ReadFileTool, WriteFileTool
from june.tooling.adapters.web_fetch import WebFetchTool

MEMORY_DB_FILE = "memory.db"
SKILLS_DIR = "skills"
SESSIONS_DB_FILE = "sessions.db"
WRITE_TOOLS = frozenset({"write_file", "manage_skill"})
SKILL_TOOLS = frozenset({"manage_skill"})


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
    agent_loop: AgentLoop
    session_closer: SessionCloser
    chat_service: ChatService
    tool_gate: ToolGate
    tool_registry: ToolRegistry
    tool_runner: ToolRunner


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


def build_file_tools(
    workspace: Path, base_dir: Path, protected_roots: Sequence[Path]
) -> list[Tool]:
    """Create the Workspace and build the confined file tools over it."""
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"workspace directory is not usable: {workspace}") from exc
    absolute_roots = tuple(base_dir / root for root in protected_roots)
    return [ReadFileTool(workspace), WriteFileTool(workspace, absolute_roots)]


def build_app(settings: Settings) -> App:
    """Build the application from explicit settings; each part is built once and shared."""
    soul = load_persona(settings)
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"data directory is not usable: {settings.data_dir}") from exc
    chat_model = build_chat_model(settings)
    embedder = build_embedder(settings)
    index = SqliteVectorIndex(settings.data_dir / MEMORY_DB_FILE)
    clock, ids = SystemClock(), UuidGenerator()
    base_dir = Path.cwd()
    protected_roots = (settings.persona_path, settings.data_dir / SKILLS_DIR)
    protected = ProtectedPaths(base_dir, protected_roots)
    memory_gate = MemoryWriteGate(memory_write_classifier(protected))
    remember_fact = RememberFact(index, embedder, clock, ids, guard=memory_gate)
    remember_episode = RememberEpisode(index, embedder, clock, ids, guard=memory_gate)
    recall = Recall(index, embedder, clock)
    summarizer = ExtractiveSummarizer()
    skill_store = GuardedSkillStore(FileSkillStore(settings.data_dir / SKILLS_DIR), memory_gate)
    session_store = SqliteSessionStore(settings.data_dir / SESSIONS_DB_FILE)
    context_builder = ContextBuilder(soul)
    agent_loop = AgentLoop(chat_model, compactor=Compactor())
    closer = SessionCloser(
        RememberConversation(summarizer, remember_episode),
        Consolidate(index, summarizer, remember_fact),
    )
    chat_service = ChatService(
        sessions=session_store,
        context_builder=context_builder,
        agent_loop=agent_loop,
        recall=recall,
        index=index,
        skills=skill_store,
        clock=clock,
        ids=ids,
        closer=closer,
        input_guard=InputGate(injection_classifier()),
        reply_guard=EndLoopGate(),
    )
    file_tools = build_file_tools(settings.workspace_dir, base_dir, protected_roots)
    tool_registry = ToolRegistry([*file_tools, WebFetchTool()])
    tool_gate = ToolGate(
        tool_registry.risks,
        protected=protected,
        write_tools=WRITE_TOOLS,
        skill_tools=SKILL_TOOLS,
    )
    tool_runner = GatedToolRunner(RegistryToolRunner(tool_registry), tool_gate)
    return App(
        settings=settings,
        soul=soul,
        chat_model=chat_model,
        embedder=embedder,
        vector_index=index,
        skill_store=skill_store,
        remember_fact=remember_fact,
        remember_episode=remember_episode,
        recall=recall,
        forget=Forget(index),
        session_store=session_store,
        context_builder=context_builder,
        agent_loop=agent_loop,
        session_closer=closer,
        chat_service=chat_service,
        tool_gate=tool_gate,
        tool_registry=tool_registry,
        tool_runner=tool_runner,
    )
